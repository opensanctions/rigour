---
description: Pre-filter name pairs before the expensive symbolic+fuzzy inner loop in nomenklatura's logic_v2 matcher. Problem statement + requirements gathering; no solution design yet.
date: 2026-04-23
tags: [rigour, nomenklatura, names, matching, performance, pruning]
status: drafting
---

# Name-matcher pruning

## Problem statement

The cross-product matcher in
`nomenklatura/matching/logic_v2/names/match.py:name_match` runs
`match_name_symbolic` for every `(query_name, result_name)` pair
after `Name.consolidate_names` deduplication. The inner function is
expensive — per pair it builds symbol pairings, runs weighted edit
similarity on unmatched parts, applies person-name alignment, and
picks the best scoring over all valid pairings. The file itself
calls out the hazard in a comment at
`match.py:193-196`:

> This combinatorial explosion is the single biggest determinant of
> the name matching speed: 1 x 1 is very fast, 2 x 5 still good, but
> 3 x 200 gets out of hand. We need to consider more ways to prune
> pairs before we do a full symbolic + fuzzy match on them.

The clearest example on the OpenSanctions production data is
Vladimir Putin: `rigour/contrib/putin_names.txt` lists 80 distinct
aliases spanning Latin, Cyrillic, Greek, Armenian, Georgian, Hangul,
CJK, Devanagari, Bengali, Kannada, Khmer, Burmese, Hebrew, Arabic,
and several romanisation conventions. Every screening query against
a dataset where Putin is a candidate pays ~80 × (query-name count)
invocations of `match_name_symbolic`.

Many of these pairs have no realistic chance of producing a
meaningful score — a query name in Arabic script has no textual
bridge to a candidate name in Thai, and the tagger-derived symbols
may or may not overlap depending on coverage in the person-names
corpus. Today they flow through the full scoring path anyway.

### Quantitative stakes (from yente `match_perf.py`)

The cost shape is measurable. `yente/examples/match_perf.py`
EXAMPLE_3 — a Person entity with 20 name variants — produces the
p99 query class in production. Per-request CPU breakdown on that
benchmark:

| Query class            | Time   | Per candidate |
|------------------------|--------|---------------|
| Person (3 names)       | ~37 ms | ~0.7 ms       |
| Company (~2 names)     | ~5 ms  | ~0.1 ms       |
| **Person (20 names)**  | **~215 ms** | **~4.3 ms** |

The heavy query fires ~5000 `match_name_symbolic` calls (20 query
names × ~5 candidate names × 50 candidates), averaging ~43 µs per
call. That is the bulk of the 260 ms per-request CPU budget.

Translating prune rate into throughput on a single process
(ignoring the Company and 3-name Person queries, which are
rounding error):

- Baseline: 260 ms CPU/req → ~3.8 req/s per process.
- 50% prune on the heavy query: 108 ms saved → ~6.6 req/s (1.7×).
- 80% prune: 172 ms saved → ~11.5 req/s (3×).

At 70 req/s prod, a 3× throughput gain collapses ~18 processes to
~6, or absorbs 3× traffic on the same fleet. The motivating
example and the production bottleneck are the same shape.

## Current pipeline — what's already short-circuited

`name_match` already has four layers of early exit before the
N × M inner loop:

1. **Schema gate.** `type_tag == UNK` → return empty. Non-LegalEntity,
   non-Thing schemas bail out before any name work.
2. **Object path.** `type_tag == OBJ` → `match_object_names`,
   a separate `strict_levenshtein` pass with no symbol pairing.
3. **Literal-comparable short-circuit.** Build
   `{name.comparable: name}` dicts on both sides; if the key sets
   intersect, return `1.0` on the longest shared key. This catches
   most of the Latin / Cyrillic / Greek / Armenian / Georgian /
   Hangul Putin variants in one shot, because `maybe_ascii` collapses
   them all onto `"vladimir putin"`. This is load-bearing for the
   trivial cross-script cases.
4. **`consolidate_names` on both sides.** Drops name-substring-
   dominated entries. Zero-recall-loss under the current
   substring rule; does nothing for same-length transliteration
   variants (see the 20-variant Ermakov list raised in design
   discussion).

After these, `match_name_symbolic` runs unconditionally on every
surviving pair. Non-latinizable aliases (Arabic, Thai, CJK, Hebrew,
Devanagari, etc.) bypass layer 3 because their `comparable` equals
`form` — no ASCII bridge — and they usually don't substring-dominate
anything, so layer 4 leaves them intact.

## Per-pair cost characterisation

`match_name_symbolic(query, result, config)`:

1. `pair_symbols(query, result)` — Rust-side, enumerates valid symbol
   pairings over `name.spans`. Cheap when symbol sets are disjoint
   (returns one empty pairing), growing when spans overlap
   combinatorially.
2. For each pairing, a per-edge scoring loop + `weighted_edit_similarity`
   on the parts not covered by any edge. The edit-similarity call is
   the main cost when pairings are lean.
3. PER names also pay `align_person_name_order` on the remainder
   parts each pairing.
4. Final aggregation picks the best-scoring pairing.

The Putin case specifically: each non-latinizable alias likely has a
small symbol set (possibly just `NAME:Qnnnn` from the corpus or
nothing at all if the name form isn't in the corpus), so layer 1
returns the empty pairing and layer 2 collapses to a single
weighted-edit pass on the whole token sets. That pass on a
4-token-vs-4-token comparison is still ~4² Levenshtein calls.
Multiplied over 80 candidates that's where the cost concentrates.

## Pruning intuitions being explored

Three signals look like they could rule a pair out without running
the scoring core. Listed in the order we expect to reason about
them; each needs data to validate.

### A. Script comparability

**Two candidate predicates, not one.** The intuition hides a design
choice between two different comparability rules:

- **Shared script.** *Q* ∩ *C* ≠ ∅ — the names share at least one
  actual script. Direct `Script` property check.
- **ASCII bridgeable.** Both *Q* ⊆ LATINIZE_SCRIPTS and
  *C* ⊆ LATINIZE_SCRIPTS — both sides can reach ASCII via
  `maybe_ascii`. This is what the existing layer-3 literal-
  `comparable` short-circuit relies on implicitly.

The pruning predicate is the **union** of these two (keep a pair
if either holds). Naming them separately matters because they have
different failure modes (see Unicode pitfalls below) and because
downstream code may want to branch on *which* predicate rescued a
pair.

**Why this might help.** Cross-script pairs that fail both
conditions (e.g. query in Thai vs candidate in Arabic) have no
text-level evidence path. The `comparable` forms don't overlap, the
individual `part.comparable` values don't overlap, and the
weighted-edit pass will score near zero.

**Prior art already in the stack.** `NamePart.latinize: bool`
exists today (flags membership in the latinizable set), and
`text_scripts(text) -> Vec<&str>` lives in `rust/src/text/scripts.rs`.
No `Name.scripts` / `NamePart.scripts` attribute is exposed yet.

**Open questions.**
- Do we need per-part scripts, or per-name-aggregate is enough?
  Mixed-script names (e.g. "Ali Khan 阿里汗") are real, and Japanese
  names routinely mix Hiragana + Katakana + Han.
- Numeric-only or Common-only parts have no script — how do they
  fold into the predicate?
- Is the latinizable bridge transitive enough in practice, or are
  there Greek-vs-Hangul pairs where `maybe_ascii` produces
  genuinely non-overlapping outputs that still shouldn't prune?
- Does "shared script" need bucketing (see CJK-unification pitfall
  below) — treating `{Han}` on both sides as "Chinese vs Japanese
  collision risk" vs trusting the scoring core to produce zero?

### B. Symbol overlap as fallback when scripts don't match

**Proposition.** Even when script comparability fails, if
`query.symbols ∩ result.symbols` is non-empty, the pair is not
prunable — the tagger has already asserted a shared entity-level
label (a `NAME:Qnnnn` from the person-names corpus, an `ORG_CLASS`,
a `NUMERIC` ordinal, a `LOCATION`, …) and the matcher should score
it.

**Why this might help.** The script gate is coarse — it over-prunes
cases where the tagger independently knows both sides are labelling
the same thing. Symbol overlap is the fallback that rescues those
pairs. Concretely, a Thai-script Putin alias and a Cyrillic-script
Putin alias both carrying `NAME:Q7747` should survive even if their
script sets are disjoint.

**Open questions.**
- Which symbol categories count? `INITIAL` almost certainly
  shouldn't — a shared "J" carries no evidence. `NUMERIC` on its own
  is weak evidence for PER but strong for ORG. The
  `Symbol.is_matchable` predicate (see `arch-name-pipeline.md`)
  may be the right gate.
- Does "non-empty overlap" suffice or do we need a minimum weight
  (e.g. weighted by `SYM_SCORES` / `SYM_WEIGHTS`)?
- How often does the tagger *actually* label non-latinizable-script
  names with shared NAME symbols today? If coverage is poor, this
  rescue path doesn't fire and the script gate over-prunes in
  practice. Needs measurement on the production corpus.

### C. Dominance pruning

**Proposition.** If, for candidates C₁ and C₂ on the result side,
C₁'s symbols are a subset of C₂'s AND C₁ shares no script with the
query that C₂ doesn't also share, then the pair (Q, C₁) is dominated
by (Q, C₂) for any query Q — C₂ carries strictly more evidence than
C₁ against the same text surface. Drop (Q, C₁).

**Why this might help.** In the Putin case, several aliases are
"vladimir putin" with different adornments (honorific, middle name,
patronymic). After symbol-set comparison, the shorter ones may
turn out to be strict subsets of the longer ones in both script
coverage and symbol payload — a form of fuzzy containment that the
strict-substring `consolidate_names` misses.

**Open questions.**
- Does the matcher actually behave monotonically in symbols? If C₂
  has a symbol C₁ lacks, is (Q, C₂) guaranteed to score ≥ (Q, C₁)
  for every Q? If not, this pruning is unsafe.
- Is this per-side (prune within `result_names` independently) or
  cross-side? Cross-side dominance is harder to reason about.
- How does this interact with the existing `consolidate_names`
  substring rule? Does it subsume it, compose with it, or conflict?

## Unicode pitfalls the pruning rule must tolerate

Design constraints from the script model that still bear on pruning
decisions. (Latin-ASCII / `comparable` cleanness has been resolved
in `rust/src/text/translit.rs` — see `maybe_ascii_latin_roundtrip`;
pruning rules can treat `comparable` as ASCII-clean for realistic
name inputs.)

- **Script ≠ language.** Cyrillic covers Russian / Ukrainian /
  Bulgarian / Serbian / Kazakh / …; Arabic covers Arabic / Persian
  / Urdu / Pashto / Uyghur / …; Latin covers everything Western
  plus Turkish, Vietnamese, Azerbaijani, and every romanisation.
  Shared-script is a necessary but weak signal.
- **Han unification.** ICU's `Script` returns `"Han"` for Chinese
  Simplified, Chinese Traditional, Japanese Kanji, and Korean
  Hanja alike. Same-script comparability admits cross-cultural
  pairs with no linguistic connection.
- **Multi-script per language.** Japanese mixes Hiragana +
  Katakana + Han; Korean can appear in Hangul or Han; Serbian is
  officially digraphic. A literal script-set equality check between
  two forms of the same person's name fails routinely.
- **Empty script sets.** Purely numeric / punctuation-only strings
  ("007", vessel hull numbers) return `[]`. The pruning rule
  needs an explicit decision — keep or drop as cross-script pairs?
- **Predicate wording matters.** The bridgeable-to-ASCII rule must
  be phrased as "both script sets ⊆ LATINIZE_SCRIPTS" to preserve
  mixed-script homoglyph handling ("Vlаdimir" with Cyrillic `а`).
  A naïve "script sets are equal" phrasing over-prunes.
- **Cross-script `comparable` collision is a hypothesis, not a
  proof.** Two ASCII-form-identical names across scripts can be
  different people. Good for sanctions-homoglyph-evasion; any
  pruning that treats collision as proven equality over-asserts.
- **Per-name vs per-part aggregation.** Aggregating scripts at the
  Name level is simpler but loses the "Park 박보검" ↔ "Park Bogum"
  case where per-part alignment would succeed. Real design axis.
- **Transliteration-convention mismatch (orthogonal).** "Shchukin"
  (BGN/PCGN) vs `maybe_ascii("Щукин")` (ICU's pick) already fails
  cross-script `comparable` today. Pruning doesn't cause or fix
  this; future missed-match investigations should attribute the
  loss correctly.

## Additional pruning signals worth evaluating

Orthogonal to the three primary intuitions. Each is cheap to
compute and could drop the cross-product size further.

- **Token-count asymmetry.** `abs(len(q.parts) - len(c.parts)) > K`
  → prune. Cheapest possible filter; catches 1-token query vs
  5-token candidate cases where the weighted-edit pass is
  dominated by the unmatched-parts penalty anyway. Threshold
  likely 2-3 for PER, looser for ORG.
- **Token-set Jaccard on `comparable`.** Compute
  `|q.tokens ∩ c.tokens| / |q.tokens ∪ c.tokens|` on the
  per-part comparable forms. Below some floor (0.1? 0.2?) → prune.
  One set intersection per pair, all-Rust; catches "share a script,
  share nothing else" pairs efficiently. Orthogonal to symbol
  overlap — fires on ordinary-word overlap the tagger never
  labelled.
- **Side-wise `comparable` equivalence-class dedup.** Extend
  `consolidate_names` behaviour: within each side, collapse Names
  whose per-part `comparable` multisets are identical (order-
  insensitive). "Putin Vladimir" and "Vladimir Putin" produce the
  same tokens in different orders and don't substring-dominate
  each other, but they'd score identically against any candidate.
  Collapsing them pre-pairing halves the cross-product on many
  real name lists without any pruning-threshold tuning.
- **Phonetic-key overlap (PER, latinizable).** For person names
  where both sides are latinizable, compute the set of
  `NamePart.metaphone` values; if the intersection is empty and
  no `INITIAL` symbols are in play, prune. Cheap (already
  precomputed on each NamePart) and orthogonal to symbol overlap
  — fires on names the tagger didn't recognise but that nonetheless
  should or shouldn't phonetically collide.
- **Pair-ordering for faster 1.0 short-circuit.** `name_match`
  already exits on `best.score == 1.0`. Sort the pair list by a
  cheap predictor (Jaccard, prefix overlap) descending so the
  most-likely-to-hit pairs run first. Doesn't reduce pairs
  considered in worst case, but reduces them dramatically in the
  common case.

Each of these needs the same "recall budget + measured baseline"
treatment as the three primary intuitions before thresholds land.

## Target shape (sketch only — not a design commitment)

Eventual landing point per the framing discussion: a function
roughly

```
names_product(queries: Set[Name], results: Set[Name])
    -> Iterable[(Name, Name)]
```

implemented Rust-side, that enumerates only the pairs worth feeding
into `match_name_symbolic`. The matcher's inner loop becomes

```python
for query_name, result_name in names_product(query_names, result_names):
    ftres, ftmatches = match_name_symbolic(query_name, result_name, config)
    ...
```

This leaves the scoring core untouched and isolates the pruning
policy behind one call. Nothing about the call shape is decided
yet — it could equally well return `(pruned_queries, pruned_results)`
and let the Python side do the cross product.

## Implementation split (design decision record)

The natural divide is **mechanism in rigour, policy in
nomenklatura**. Rigour owns generic name-engine primitives with no
schema or matcher awareness; nomenklatura owns the matcher-
specific composition.

### Primitives to add in rigour

All additive, no breaking changes to existing APIs.

- **`common_scripts(a: &str, b: &str) -> Set<&'static str>`** —
  thin utility over `text_scripts(a) ∩ text_scripts(b)`. Operates
  on **strings, not Name objects** — the caller passes whichever
  form they want to compare (`name.comparable` for bridge-aware
  comparability, `name.form` or `name.original` for direct script
  overlap). Keeping it string-typed avoids coupling to the Name
  type and keeps the primitive reusable outside the matcher.
- **`Name.scripts` / `NamePart.scripts`** as eager fields,
  populated at construction. ICU's script lookup is already
  running per codepoint during tokenisation; caching the set per
  Name is a few bytes and saves the recomputation on every
  predicate call.
- **`Name.is_latinizable() -> bool`** (or equivalent). Wraps
  `should_ascii(name.form)` as a Name-level accessor so callers
  don't have to reach into `text` utilities.

Out of scope for rigour: thresholds, symbol-category policy,
dominance rules, anything that reads `nm_*` config keys.

### `names_product` lives in `logic_v2`

The cross-product orchestrator stays in
`nomenklatura/matching/logic_v2/names/` because it composes matcher-
specific policy: which symbol categories count, what Jaccard floor,
how dominance interacts with the scoring monotonicity of logic_v2
specifically, thresholds tuned against matcher benchmarks.

The matcher's inner loop becomes:

```python
for query_name, result_name in names_product(query_names, result_names, config):
    ftres, _ = match_name_symbolic(query_name, result_name, config)
    ...
```

#### Sketch 1: basic script-or-symbol gate

Simplest version — keep any pair with script overlap OR any symbol
overlap. First milestone; easy to measure.

```python
# nomenklatura/matching/logic_v2/names/names_product.py
def names_product(queries, results, config):
    for q in queries:
        for c in results:
            if not _keep_pair(q, c, config):
                continue
            yield (q, c)

def _keep_pair(q, c, config):
    if common_scripts(q.comparable, c.comparable):
        return True
    if q.symbols & c.symbols:
        return True  # symbol-overlap rescue
    return False
```

#### Sketch 2: dominance-aware symbol rescue

Same gate on script overlap — always let script-sharing pairs
through. The symbol-overlap rescue is tightened: among pairs for
the same query that have no script overlap, drop those whose
symbol overlap is a strict subset of another pair's overlap.
Weaker symbolic evidence is subsumed by stronger evidence for the
same query; no reason to score both.

Important efficiency note: `name.symbols` is not free — the getter
walks `name.spans` and builds the set on each access. Materialise
once per Name, not per pair. At `|Q| × |R|` pairs that's the
difference between `|Q| + |R|` and `|Q| × |R|` symbol accesses.

```python
# nomenklatura/matching/logic_v2/names/names_product.py
def names_product(queries, results, config):
    # Materialise symbols once per Name; the getter is not free.
    q_syms = [(q, frozenset(q.symbols)) for q in queries]
    r_syms = [(r, frozenset(r.symbols)) for r in results]

    # First pass: script-ok pairs go through; symbol-only pairs are
    # bucketed per query for the dominance check.
    script_ok: list[tuple[Name, Name]] = []
    per_query_symbol: dict[Name, list[tuple[Name, frozenset]]] = {}
    for q, qs in q_syms:
        for r, rs in r_syms:
            if common_scripts(q.comparable, r.comparable):
                script_ok.append((q, r))
                continue
            overlap = qs & rs
            if overlap:
                per_query_symbol.setdefault(q, []).append((r, overlap))

    # Script-ok pairs survive unconditionally.
    yield from script_ok

    # Symbol-only pairs: drop those whose overlap is a strict subset
    # of another pair's overlap for the same query. Equal overlaps
    # all survive (no strict-subset relationship).
    for q, cands in per_query_symbol.items():
        overlaps = [o for _, o in cands]
        for r, overlap in cands:
            if any(overlap < other for other in overlaps):
                continue  # strictly dominated — skip
            yield (q, r)
```

Cost characterisation:
- `name.symbols`: exactly `|Q| + |R|` calls total, not per pair.
- `common_scripts`: one call per pair, but on pre-latinised
  `.comparable` strings — ICU-cached script lookups + small set
  intersection. Cheap.
- Dominance: `O(K²)` per query where `K` is the number of symbol-
  only candidates for that query. `K` is typically small — it's
  the exotic-script rescue subset, which is where the expensive
  scoring would otherwise land.

Open policy questions raised by this variant:
- **Symmetry.** Per-query-only dominance is the conservative
  default. Running dominance symmetrically (a pair survives only
  if its overlap is superset-maximal for both its query and its
  candidate) prunes harder but risks cascading drops — a pair's
  survival depends on what else is in both sets.
- **Matchable-only symbols.** Should the overlap be computed on
  `{s for s in q.symbols if s.is_matchable}` instead of raw
  `q.symbols`? The `Symbol.is_matchable` predicate excludes
  INITIAL, so a single shared "J" doesn't falsely rescue a pair.
- **Weight floor.** Is a single `{NUMERIC:5}` overlap enough to
  rescue a PER pair? A cheap check against `SYM_WEIGHTS` /
  `SYM_SCORES` (already defined in `logic_v2/names/magic.py`)
  could gate the rescue below a total-weight threshold.

### Migration path

1. Land the three rigour primitives (`common_scripts`,
   `Name.scripts`, `Name.is_latinizable`). Pure additive, no
   downstream changes required.
2. Implement `names_product` in `logic_v2` using those primitives.
   Start with the simplest predicates (script overlap or symbol
   overlap); add Jaccard / dominance / pair-ordering behind flags
   as measurements justify each.
3. Measure on `match_perf.py`. Validate prune rate and recall
   impact against the budget.
4. If step 3 surfaces orchestration overhead as the bottleneck
   (unexpected but possible), revisit the Rust-side filter-composer
   option with real data.

## Requirements to gather before designing

1. **Measured baseline.** Per-pair time distribution in
   `match_name_symbolic` on a realistic corpus slice (Putin queries,
   PER cross-matching in general). Which pairs are cheap (disjoint
   symbols, small parts) vs expensive (dense spans)?
2. **Recall impact budget.** Acceptable false-negative rate from
   pruning. Sanctions matching has asymmetric cost — a missed match
   is worse than a noisy score — so the bar is high. Need a number
   before picking thresholds.
3. **Symbol coverage on non-latinizable names.** Tagger output per
   script family on the production dataset. If Thai/CJK/Arabic
   coverage in the person-names corpus is ~0, the symbol-overlap
   rescue (intuition B) doesn't fire and the script gate
   over-prunes. Measurement gates the whole design.
4. **Script taxonomy.** ICU script long-names directly, or a
   bucketed equivalence set? Does `{Han}` need splitting into
   CJK-language buckets? Does Japanese need a virtual bucket
   covering Hiragana + Katakana + Han? Defer until production data
   shows whether the raw ICU set suffices.
5. **Per-name vs per-part aggregation.** Script comparability at
   Name level (cheap, misses "Park 박보검" ↔ "Park Bogum") vs
   NamePart level (costlier, rescues it). Pick before API.
6. **Where does `Name.scripts` / `NamePart.scripts` live?** Eager
   field populated at construction (ICU already called per
   codepoint during tokenisation) vs lazy. Eager is the default
   assumption.
7. **Monotonicity check for dominance.** Is
   `score(Q, C₂) ≥ score(Q, C₁)` whenever C₁.symbols ⊆ C₂.symbols
   and C₁.tokens ⊆ C₂.tokens? Small formal or empirical check
   before relying on the ordering.
8. **Interaction with existing filters.** Pruning must not regress
   the layer-3 literal-`comparable` short-circuit, and must have a
   defined interaction with `consolidate_names` (before, after, or
   replacing).
9. **Matcher-side vs rigour-side.** `names_product` could live in
   rigour (pure name logic) or in nomenklatura (matcher-specific).
   Rigour is the likely home; pinning it down shapes the API.
10. **Empty-script-set behaviour.** Numeric-only / punctuation-only
    names ("007") have `text_scripts == []`. Keep or drop
    cross-script pairs where at least one side is empty?

## Non-goals for this document

- Proposing a specific algorithm for any of the three rules.
- Committing to an API shape, signature, or return type.
- Deciding thresholds (edit-distance cutoffs, symbol-weight floors,
  script-equivalence classes).
- Addressing the "many transliteration variants" problem (Ermakov
  list / fuzzy-cluster reduction) — that's a separate plan in the
  `reduce_names`/`reduce_transliterations` direction.
- Touching the scoring core itself. Pruning is additive; the
  scoring math stays as-is for every pair that survives.

## Related

- `plans/arch-name-pipeline.md` — `entity_names`, `analyze_names`,
  the `consolidate` flag, and the `Name` / `Symbol` object graph
  this plan builds on. Also covers `reduce_names` (casefold-only
  dedup), a sibling primitive to the transliteration-reduction
  concern mentioned above.
- `nomenklatura/matching/logic_v2/names/match.py` — the current
  N × M loop and its `# This combinatorial explosion…` comment,
  which is the motivating site for this work.
- `rigour/contrib/putin_names.txt` — the 80-alias worked-example
  dataset.
- `yente/examples/match_perf.py` — production benchmark that
  quantifies the heavy query class (EXAMPLE_3, 20 name variants).
  Use as the baseline measurement harness when validating prune
  rates.

### Adjacent filter layers (out of scope, stack multiplicatively)

`names_product` prunes at the name level. The same measurement
pass will likely surface cheaper pre-filters at the matcher-
orchestration level that stack in front of name matching entirely:

- **Country / territory overlap.** If a candidate entity shares no
  country or territory with the query, skip name matching on that
  candidate wholesale.
- **DOB range gate.** For Person entities, DOB mismatch beyond
  plausible tolerance is a hard skip.
- **Schema compatibility.** A Person query against a Vessel
  candidate already bails via `schema_type_tag == UNK`, but
  finer-grained gates (e.g. Organization-vs-Company strictness)
  may apply.

These live in nomenklatura, not rigour, but instrumenting them
alongside name pruning is cheap and the gains stack (a 2× prune
at the orchestration layer and 3× at the name layer is 6×
end-to-end). Worth tracking but out of scope for this plan.
