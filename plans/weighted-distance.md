---
description: Move nomenklatura's name-part fuzzy distance into rigour as a Rust primitive. Spec-driven redesign (not faithful port), iterated on a harness with a Python baseline before any Rust work.
date: 2026-04-28
tags: [rigour, nomenklatura, names, distance, rapidfuzz, performance]
status: drafting
---

# Weighted name-part distance

## Goal

Move the inner loop of nomenklatura's name-part fuzzy matcher
(`weighted_edit_similarity`) into rigour's Rust core, so that the
hot path of `match_name_symbolic` doesn't iterate opcodes and
characters in Python on every surviving `(query_name,
result_name)` pair.

## Fixed premises

- **`Match` stays in nomenklatura.** It carries matcher-policy
  fields (`weight`, `symbol`, `is_family_name`) and is consumed
  outside the distance computation. The Rust primitive returns
  raw alignment data (per-part costs + per-part overlap) and
  nomenklatura assembles `Match` objects from it. Rigour does
  not learn about `Match`.
- **`NamePart` already lives in Rust** (see
  `arch-name-pipeline.md`). The API is in NamePart terms —
  a `Vec<NamePart>` per side. Generic string+offsets shape was
  considered and rejected: NamePart is the language rigour
  speaks for names, and the only consumer is a name matcher.
- **Scoring drift is permitted.** This is a redesign, not a
  faithful port. The current Python implementation has
  accidents-of-evolution baked in (the `0.51` overlap
  threshold, the `log_{2.35}` budget, the SEP-drop cost of
  0.2). The Rust replacement should produce defensible,
  spec-driven results. If they differ from the current,
  that's fine — the `checks.yml` + nomenklatura unit-test
  bar (below) is the constraint, not bit-for-bit equivalence.
- **`names_product` pruning lands first.** The pre-filter
  pipeline is treated as the baseline. The Rust primitive
  is designed for the input distribution that survives it
  (see "Where in the pipeline this primitive sits" below).
- The architectural premise from `arch-rust-core.md` —
  *"port larger chunks; the hot loop has to run entirely in Rust,
  crossing the Python boundary only at coarse entry/exit
  points"* — is why this primitive exists at all.

## Measured baseline

`nomenklatura/contrib/name_benchmark/logic_v2_13_rel4_8.perf`
(452 000 compares, 65.35 s total) is the reference profile.
**Important caveat:** the benchmark loops the ~400 fixed
`checks.yml` cases ~2 000 times, so every `(qry_text,
res_text)` pair sees the LRU after the first iteration. Cache
behaviour observed here is not representative of production
yente traffic. Distance / cost numbers per pair are
representative; cache-hit ratios are not.

Hot-path numbers:

| Item                          | Self    | Cum.   | Calls   | Notes                |
|-------------------------------|---------|--------|---------|----------------------|
| `compare` (total)             | 6.01 s  | 63.2 s | 452 000 | matcher entry point  |
| `name_match`                  | 1.98 s  | 34.7 s | 452 000 |                      |
| `match_name_symbolic`         | 3.68 s  | 27.0 s | 392 000 |                      |
| **`weighted_edit_similarity`**| **5.63 s** | **11.0 s** | **390 000** | **~17 % of total** |
| `_edit_cost`                  | 1.26 s  | 1.46 s | 4.59 M  | ~320 ns/call         |
| `_costs_similarity`           | 0.45 s  | 0.77 s | 644 000 |                      |
| **`_opcodes`** (rapidfuzz)    | —       | **0.002 s** | **154** | **LRU 99.96 % hit** |
| `pair_symbols` (Rust)         | 5.66 s  | 7.17 s | 392 000 | already in Rust      |

Three observations dominate the design:

1. **`_opcodes` looks free, but only because of the benchmark
   shape.** 154 cache misses across 390 000 calls — the
   `MEMO_BATCH=1024` LRU absorbs the workload because the same
   ~400 cases recur ~2 000 times. The 154 misses cost ~2 ms
   in aggregate, i.e. **~13 µs per genuine C++ opcodes call.**
   At a hypothetical 0 % hit rate (every pair unique) that
   reprices to 390 000 × 13 µs ≈ 5 s — comparable to the
   Python-iteration cost. Production will sit somewhere
   between these poles: the `MEMO_BATCH=1024` LRU is small
   relative to a real query day's distinct name pairs, so
   real hit rates are well below 99.96 %.

   This still **kills option C** below (porting Hyyrö 2003 to
   Rust). The 13 µs per-call C++ figure is what bit-parallel
   currently buys; even at full miss rate, replacing it with
   plain Rust DP at ~12 chars per pair (~1 µs at 1 ns/cell on
   a ~12×12 matrix) is not worse — and the same Rust call
   subsumes the iteration that costs 5.6 s on the benchmark.
   We aren't trying to beat SIMD; we're folding it and the
   surrounding Python loop into one Rust pass.
2. **Per-pair work averages ~12 character ops** (4.59 M
   `_edit_cost` calls / 390 k function calls). `comparable`
   forms in this corpus are 5-15 chars — exactly the regime
   where plain Wagner-Fischer is microsecond-cheap regardless
   of bit-parallelism.
3. **`weighted_edit_similarity` is 17 % of the matcher
   end-to-end on this benchmark** (11.0 s of 63.2 s). On
   production traffic the share is plausibly *higher*, because
   the rapidfuzz cost re-emerges from behind the LRU and
   inflates the function's cumulative time without inflating
   the surrounding `compare`/`name_match` overhead by the same
   factor. The inline's win therefore probably scales up off
   this benchmark, not down.

   Either way it stacks multiplicatively with the orthogonal
   `names_product` pruning work in
   `plans/name-matcher-pruning.md`. Both levers are worth
   pulling; neither is a single-shot revolution.

## Source 1: RapidFuzz Indel (Python)

`rapidfuzz.distance.Indel` and `rapidfuzz.distance.Levenshtein`
both ship Heikki Hyyrö's bit-parallel algorithms in C++:

- **Distance** computation is bit-parallel: for strings ≤64
  characters after affix removal, individual character
  processing using the Myers/Hyyrö encoding; for longer strings,
  blockwise processing 64 characters at a time. Worst-case
  `O(⌈N/64⌉·M)`.
- **Alignment** (`opcodes()`, `editops()`) recovers the actual
  edit-script. `Editops` is a flat list of `(tag, src_pos,
  dest_pos)`; `Opcodes` groups them into runs of `equal` /
  `replace` / `insert` / `delete` with `(tag, src_start, src_end,
  dest_start, dest_end)`. Same DP, plus a Hyyrö 2003-style
  bit-parallel traceback in C++.
- **Indel** (the page named in the brief) is Levenshtein with
  substitutions weighted at 2 — equivalent to "insertions and
  deletions only". It exposes the same surface (`distance`,
  `similarity`, `normalized_*`, `editops`, `opcodes`,
  `BatchComparator`).

`Indel` is **not** what nomenklatura currently uses;
`weighted_edit_similarity` calls `Levenshtein.opcodes(qry,
res)`. The Indel page is referenced as a reminder that the
RapidFuzz API surface is the same shape across distance metrics
and that switching to Indel-style "insertions-and-deletions"
costing is a parameter knob, not a re-architecture.

### What the Rust `rapidfuzz` 0.5 crate exposes

Reality check before designing:

- `levenshtein::distance` / `_with_args` / `BatchComparator`,
  `WeightTable` (custom per-edit-type weights), `score_cutoff`,
  `score_hint`. Bit-parallel internally — same engine as the C++
  side, just less surface.
- `damerau_levenshtein::*` — same shape.
- `indel::*` — same shape.
- **No `opcodes()`. No `editops()`.** No alignment recovery on
  any of the distance modules.

This is the live "rapidfuzz opcodes gap" already documented in
`arch-rust-core.md` under *Open questions / Distance / rapidfuzz
opcodes gap*. Status quo plan-of-record there is "keep Python
rapidfuzz for distance + opcodes." This plan is the one that
revisits that decision.

## Where in the pipeline this primitive sits

The matcher does four sequential stages before the weighted-edit
function ever sees a token. By the time `weighted_part_alignment`
is called, the input has been heavily filtered:

1. **Name picking / pruning.** `names_product` (see
   `plans/name-matcher-pruning.md`, now landed) drops pairs
   that have no script bridge and no symbol overlap — Thai vs
   Cyrillic, etc. By the time a pair reaches the inner loop,
   there's at least a plausible textual or symbolic
   alignment path.
2. **Symbolic alignment.** `pair_symbols` matches known terms
   that the rigour tagger has labelled on both sides — person
   names from the corpus ("Jeff" → `NAME:Q...`), org-class
   fragments ("Holding", "LLC" → `ORG_CLASS:...`), numerics,
   ordinals. These score independently of string distance,
   weighted by `SYM_SCORES` / `SYM_WEIGHTS`.
3. **Person-name reordering on the residue.** For PER, the
   tokens left over from step 2 are run through
   `align_person_name_order` — "Buckley, Jeff" and
   "Jeff Buckley" arrive at the distance function already
   permuted into a comparable order based on `NamePartTag`
   (given before family, etc.). For ORG/ENT, `tag_sort` does
   the same job by tag.
4. **Weighted-edit on the residue.** *This is the function
   we're designing.* It scores the alignment of leftover
   tokens — the ones the symbol layer didn't recognise.

What this means for the design:

- **Inputs are short and low-information.** The recognised
  tokens have already been peeled off. What's left is the
  ambiguous tail: misspellings, transliterations the tagger
  doesn't know, partial names, surface-form drift.
- **Inputs are order-aligned.** Step 3 makes positional
  comparison meaningful — the first remaining query token
  corresponds to the first remaining result token at the
  type-tag level.
- **Inputs are script-comparable.** Step 1 guarantees a
  textual or symbolic bridge exists. The function isn't
  asked to score Thai vs Cyrillic.

The spec below is written for this input distribution, not
for arbitrary token pairs.

## Spec

### Purpose

Score the alignment of token residue (post-prune,
post-symbol-pair, post-tag-sort) and assign every input token
to exactly one returned record — paired or solo. The function's
output drives downstream score aggregation in `match.py`
(extra-token penalties, family-name boost, final pairing
score).

### Score semantics

Per-pairing score is in `[0, 1]`. **The score is a ranking
signal, not a probability** — see `name-screening.md` for the
industry context. Higher scores mean stronger evidence that
the tokens refer to the same thing; the consumer (logic_v2)
chooses where to set the alert threshold.

- `1.0` — these tokens are clearly the same.
- `0.7` — the logic-v2 alert-to-human bar; output above this
  means "worth a person looking at." Sits at the bottom of
  the industry-typical "urgent human review" band (75-89%).
- `0.0` — no evidence.

The function does not claim "score = P(match)" — it claims
monotonicity and a useful response curve.

Sanctions context is recall-protective. A false negative
(missed sanctions hit) is more costly than a false positive
(human review). Where the spec offers margin, err toward
keeping borderline matches.

### Score response curve

The score function must produce a *confidence cliff*: most of
the mass at the extremes, fast transition through the
mid-range. This is what makes the industry-standard threshold
banding (60 / 75 / 90) operationally useful. See
`name-screening.md` for the broader rationale.

Target distribution:

| Match quality                          | Target score |
|----------------------------------------|--------------|
| Exact / 1 typo in long token           | ≥ 0.95       |
| Plausible match (1-2 char ambiguity)   | 0.70 – 0.85  |
| Borderline (transliteration drift)     | 0.40 – 0.70  |
| Clear non-match                        | < 0.30       |

The empty middle is intentional. Per-side product (`q_sim ·
r_sim`) currently produces this shape via punitive squashing —
`0.99² ≈ 0.98` (preserved), `0.7² ≈ 0.49` (collapsed).
Replacement combination functions must preserve the cliff or
have a defensible reason not to. Geometric mean specifically
*softens* the cliff and is probably wrong on those grounds.

### Configurability: one core, tunable bias

Two consumer scenarios — KYC at customer onboarding (lower
threshold, recall-leaning) and payment / transaction
screening (higher threshold, precision-leaning) — share the
same scoring core. Differences are expressed as bias on the
budget cap, not as separate scoring functions.

The existing `nm_fuzzy_cutoff_factor` in `ScoringConfig`
multiplies into the budget cap and is the right knob; the
function plumbs that bias through without bifurcating the
math. logic_v2 ships defaults; downstream consumers (yente,
internal tools) override per scenario. See
`name-screening.md` for the full picture.

### Symmetry

Default symmetric in `(qry_parts, res_parts)`. Asymmetry is
permitted if a concrete case justifies it — the query and
candidate have different semantic roles — but not required
by default. Returned-record ordering is not load-bearing
(downstream sorts before display).

### Completeness invariant

**Every input NamePart appears in exactly one returned
record.** Either:

- in a paired record (with at least one partner from the
  other side), or
- as a solo record (one side empty, the other side a
  single NamePart).

No NamePart is silently dropped. This is what gives
`match.py` a correct handle on extra-token penalties via
`extra_query_name` / `extra_result_name`.

### Cross-boundary character flow

Two flow patterns are first-class. Both must work without
special-casing.

1. **Token merge / split.** "vanderbilt" ↔ "van der bilt".
   Lone SEP (gained or lost on one side) costs ~0.2 — almost
   free.
2. **Token interspersal.** "john smith" ↔ "rupert john
   walker smith". Whole extra tokens flow into solo records
   without dragging down the matched tokens. "john" and
   "smith" still pair at score 1.0 each; "rupert" and
   "walker" surface as solo unmatched on the result side.

The implementation must score across token boundaries, not
just within tokens. Per-token pre-alignment with explicit
merge/split rules was considered and rejected — it doesn't
handle interspersal cleanly.

### Cost model

The DP is parameterised by a uniform char-pair cost function.
Cost depends on the `(char_q, char_r)` pair, **not** on whether
the DP labels the step substitute, insert, or delete. This
removes the inconsistency in the current Python where
`SIMILAR_PAIRS` only fires on substitution.

| Edit                                      | Cost  | Why |
|-------------------------------------------|-------|-----|
| Equal characters (incl. equal SEP)        | 0.0   | exact |
| Confusable pair (visual/phonetic table)   | 0.7   | typo / OCR / transliteration noise |
| SEP gained or lost on one side            | 0.2   | token merge or split |
| Default substitute / insert / delete      | 1.0   | character-level noise |
| Digit-involved mismatch (no confusable)   | 1.5   | digits identify specific things |

Notes on the table:

- "fund 5" vs "fund 8" — digit-vs-digit-different lands at
  1.5. Digit difference is the punitive tier.
- `(5, s)`, `(0, o)`, `(1, l)` etc. take the confusable cost
  (0.7), not the digit cost. **Confusable beats digit when
  both could fire.**
- Equal SEP is free (token boundary preserved on both sides).
- SEP-substitute-letter takes default cost 1.0; we don't
  distinguish "letter near a boundary" from "letter at
  position N."

### Pairing rule (parts → records)

Two NameParts pair into the same record iff the alignment
connects them — i.e. at least one equal-character step in
the DP traceback maps a character of one to a character of
the other. Pairing is transitive: A↔B and B↔C produce one
record `{qps=[…A…], rps=[…B…C…]}`.

Replaces the current 51%-of-shorter overlap threshold. With
the input distribution this function actually sees (post-
pruning short residue), the threshold rarely fires
meaningfully, and "alignment connectivity" is the principled
expression of "characters from this part went to that part."

### Per-record score

Per record cluster:

1. Compute per-side similarity from per-part costs accumulated
   during the alignment, normalised by character length.
2. Apply a length-dependent budget cap: if total cost on either
   side exceeds the budget, score is 0. The budget grows
   sub-linearly with length and falls to ~0 for very short
   tokens (gates fuzzy matching off below 3-4 chars — relevant
   for 2-char Chinese given names that survive earlier prune
   stages).
3. Combine per-side similarities into a single score in
   `[0, 1]`.

The exact functional choices (combination function, budget
shape) are deferred to the test-harness-driven iteration
(see below).

### Stopword down-weighting

Stopword tokens contribute lower weight to the aggregated
score. Spec: weight reduces in proportion to stopword
content of the cluster, regardless of cluster size. The
current Python "1×1 only" rule was a perf shortcut, not
principled.

Exact curve (linear-in-fraction vs threshold vs exponential)
deferred to harness iteration.

### Solo records

Every input NamePart not assigned to a paired record becomes
a solo record (`qps=[part]` with empty `rps`, or vice versa).
Solo records feed `extra_query_name` / `extra_result_name`
weight policies in `match.py` and are essential to the
completeness invariant.

### Determinism

Same inputs produce identical outputs. Returned-record
ordering doesn't have to be stable across implementations
(downstream sorts), but per-implementation it should be a
deterministic function of the inputs.

### Input contracts (assumed, not checked)

`analyze_names` guarantees:

- Every NamePart has a non-empty `comparable` (≥ 1 char).
- `comparable` is casefolded and whitespace-squashed.
- Tag ordering on inputs is canonicalised (PER via
  `align_person_name_order`, ORG via `tag_sort`).

The function does not re-validate.

## Source 2: nomenklatura `distance.py`

`nomenklatura/matching/logic_v2/names/distance.py` is the Python
module to inline. Two public entry points:

- **`strict_levenshtein(left, right, max_rate=4) -> float`**
  (lines 34-46). Already a thin wrapper over rigour's
  `levenshtein` with a max-edits cutoff and a power-curve
  similarity. Used only by `match_object_names` (vessels, etc.).
  Out of scope for this port — already cheap, no opcodes needed.
- **`weighted_edit_similarity(qry_parts, res_parts, config) ->
  List[Match]`** (lines 93-184). The actual target.

### What `weighted_edit_similarity` does

Inputs: two lists of `NamePart` (the query-side and result-side
remainders that survived the symbol-pairing step in
`match.py`), plus a `ScoringConfig`.

Outputs: a list of `Match` objects whose `qps`/`rps`/`score`
fields are populated from the alignment and whose `weight` is
adjusted (`0.7` for stopword-only matches; `1.0` otherwise — the
family-name boost happens later, in `match.py`).

Steps:

1. **Build SEP-joined strings** from `comparable` forms:
   `qry_text = " ".join(p.comparable for p in qry_parts)`,
   same for result. SEP is a single space, used as an
   alignment-internal token boundary.
2. **`_opcodes(qry_text, res_text)`** — `@lru_cache`d call to
   `Levenshtein.opcodes(...)`. Returns the runs of equal /
   replace / insert / delete spans on the SEP-joined string.
3. **Walk the opcodes character-by-character** using
   `zip_longest(qry_span, res_span, fillvalue=None)`:
   - Maintain `qry_idx` / `res_idx` cursors into the part lists,
     advancing whenever the current side consumed a SEP. The
     cursor identifies which `NamePart` the current character
     belongs to.
   - On `equal` chars (non-SEP on both sides), increment
     `overlaps[(qry_cur, res_cur)]` — this is the running count
     of matching characters between the current query part and
     current result part.
   - On every char (on either side), append `_edit_cost(op,
     qc, rc)` to `costs[qry_cur]` / `costs[res_cur]` per side
     that contributed a character.
4. **`_edit_cost`** is the weighted-edit cost table:
   - `equal` → 0.0
   - `(SEP, None)` or `(None, SEP)` (lone separator drop) → 0.2
   - `(qc, rc) ∈ SIMILAR_PAIRS` (visual / phonetic confusables
     like `0`/`o`, `1`/`l`, `5`/`s`, …) → 0.7
   - either side `isdigit()` → 1.5 (digits resist being treated
     as edit fodder)
   - default → 1.0
5. **Build matches from overlap density**: for each
   `(qry_cur, res_cur)` pair with `overlap / min(len(qp), len(rp))
   > 0.51`, fold into a `Match` via union-find-by-presence
   (already-seen on either side joins the existing Match).
6. **Score per match** via `_costs_similarity`:
   - `max_cost = log_{2.35}(max(len(costs)-2, 1)) * bias` —
     log-budget on edits, deliberately tight for short names
     (Chinese 2-char names get `log(0,2.35)·bias = -∞` ⇒
     fuzzy disabled), generous-but-bounded for long names.
   - If `total_cost > max_cost`, score 0.
   - Otherwise `1 - (total_cost / len(costs))`.
   - Final `match.score = q_sim · r_sim` (multiplied across
     sides; either side too noisy zeros the match).
   - Bias `nm_fuzzy_cutoff_factor` is read from `ScoringConfig`.
7. **Stopword down-weight** (line 160-162): a 1×1 match where
   the single query part is a stopword (`is_stopword(form)`)
   has its `weight` set to 0.7. This is the only weight
   adjustment that lives inside this function — everything else
   (`extra_query_name`, `extra_result_name`, `family_name_weight`)
   happens in `match.py` after this returns.
8. **Unmatched parts** (lines 173-182): every query part not in
   `part_matches` becomes a solo `Match(qps=[qp])`; same for
   result.

### How `match.py` consumes it

`match_name_symbolic` (lines 24-113) calls
`weighted_edit_similarity` once per pairing, after symbol
edges have been peeled off:

```python
matches.extend(weighted_edit_similarity(query_rem, result_rem, config))
```

The returned `Match` list is then post-processed in `match.py`:

- Empty-side matches get `extra_query_name` / `extra_result_name`
  weight bias.
- All-`comparable`-equal matches are forced to `score=1.0`
  (literal-equality override).
- Family-name matches get `family_name_weight` multiplier.
- The matches are summed (weighted score / weight) into the
  pairing's overall score.

These post-passes don't move; they stay in `match.py`. The
inlining boundary is exactly the `weighted_edit_similarity` call.

## The inlining design

### Shape of the Rust primitive

```rust
// rust/src/names/distance.rs (new module)
pub struct PartCosts {
    pub qry_costs: Vec<Vec<f64>>,   // costs[i] = cost stream for qry_parts[i]
    pub res_costs: Vec<Vec<f64>>,
    pub overlaps: Vec<(usize, usize, u32)>,  // (q_idx, r_idx, char_overlap)
}

#[pyfunction]
pub fn weighted_part_alignment(
    qry_parts: Vec<PyRef<NamePart>>,
    res_parts: Vec<PyRef<NamePart>>,
) -> PartCosts;
```

Python side (nomenklatura):

```python
def weighted_edit_similarity(qry_parts, res_parts, config):
    align = weighted_part_alignment(qry_parts, res_parts)
    # ... build Matches from align.overlaps + costs, apply
    # _costs_similarity, stopword weight, etc.
```

What stays Python:
- `Match` construction.
- `is_stopword` weight gate.
- `_costs_similarity` (`config.get_float(...)` access; trivial
  arithmetic). Could also move to Rust if we pass `bias` in,
  but the saving is tiny and keeping it Python keeps `Match`
  assembly local.

What moves to Rust:
- The opcodes computation.
- The character-by-character walk that fills `costs` and
  `overlaps`.
- `_edit_cost` (the SIMILAR_PAIRS / SEP / isdigit table).

This is the line at which the Python-side loop collapses. Every
part of the work that scales with `len(qry_text) + len(res_text)`
is in Rust; the Python side only iterates the `O(parts)`
overlaps + `O(matches)` Match list.

### The opcodes problem

Rust `rapidfuzz` 0.5 has no `opcodes()`. Three options:

**A. Status quo + thin Rust wrapper.** Keep
`weighted_edit_similarity` in Python. Don't port. Accept the
char-by-char Python loop as the cost of admission to `rapidfuzz`'s
SIMD bit-parallel alignment.

- Pro: zero implementation cost; `rapidfuzz`'s C++ alignment is
  the reference quality bar for opcodes.
- Con: doesn't address the actual hot loop. The opcodes call is
  `@lru_cache`d — most of the per-pair time is the Python `for
  op in opcodes: for qc, rc in zip_longest(...)` walk, not the
  opcodes call itself.

**B. Rust Wagner-Fischer with full traceback.**
Implement plain DP (`O(NM)` time + space) in Rust, with
backtrack from `(N, M)` recovering the edit script.

- Pro: ~50 lines of Rust. Total clarity. Lets us fold the
  weighted-cost function *into* the DP if we want (see "Optimal
  vs. faithful alignment" below). Returns whatever shape we
  want — opcodes, editops, or directly the per-part cost
  stream.
- Con: not bit-parallel. For typical name lengths (`comparable`
  forms 5-30 chars) the matrix is ~150-900 cells. Rust at
  ~1ns/cell vs C++ bit-parallel at ~1ns per 64-cell block.
  Worst case ~50× slower on the DP itself, but the DP is
  already a small fraction of per-pair time.

**C. Port Hyyrö 2003 bit-parallel alignment to Rust.**
Reimplement the C++ `rapidfuzz` traceback in Rust, possibly
upstreaming to the `rapidfuzz` crate.

- Pro: full speed parity with Python. Eventually benefits the
  whole Rust ecosystem.
- Con: serious implementation effort. Hyyrö's algorithm is
  subtle — the bit-parallel encoding tracks horizontal /
  vertical / diagonal carry bits; getting the traceback right
  requires careful porting. Real risk of correctness bugs in
  exotic Unicode cases. Out of proportion for a single
  consumer.

### Recommendation: B

Plain Wagner-Fischer in Rust is the right call, with the
profile data backing each reason:

1. **The DP isn't the bottleneck on this benchmark, and won't
   be in production either.** `_opcodes` cumulative time is
   2 ms across 390 000 calls — but only because the benchmark's
   2 000-fold repetition keeps the LRU saturated; per-genuine-
   call cost is ~13 µs. Even fully un-cached (production
   worst-case), the 5.63 s self-time of
   `weighted_edit_similarity` — the Python iteration over the
   opcodes plus `_edit_cost` (1.46 s alone across 4.59 M
   calls) — is the larger share. Moving that iteration into
   Rust is the prize.
2. **Name strings are short.** ~12 char ops per call on the
   benchmark. `O(NM)` plain DP at these sizes is single-µs
   territory in Rust. Bit-parallel would shave nanoseconds off
   a function whose Python iteration costs microseconds.
3. **It enables the cost-folding refactor** (next section).
   Bit-parallel alignment is fixed at unit costs; if we ever
   want the alignment to be optimal under the *weighted*
   cost model, plain DP is the only path.

Status quo (A) leaves the 5.63 s of Python-iteration overhead
on the table. Bit-parallel (C) tries to optimise a 2 ms phase
that's already ~free. Plain DP (B) is the only option that
addresses the actual cost.

### Honest sizing of the win

`weighted_edit_similarity` is 17 % of the matcher end-to-end
on this benchmark. Realistic best case for the inline:

- Move the opcodes computation, the per-char walk, `_edit_cost`,
  and the cost-list / overlap accumulation to Rust. That's
  ~70-80 % of the function's cumulative time.
- `_costs_similarity`, the stopword gate, the `Match`
  assembly, the unmatched-parts emission stay Python.
- Net saving on the function on this profile: ~7-8 s of the
  current 11 s cumulative → ~10-12 % end-to-end.

**This is the lower bound.** Production traffic has a much
colder LRU; the un-cached `_opcodes` cost re-emerges and the
inline absorbs that work too (a single Rust pass replaces the
opcodes call *and* the iteration over its output). The
end-to-end win on real workloads is plausibly larger than the
benchmark suggests, possibly meaningfully so. We won't know
until we measure on a yente-shaped workload.

The bigger lever is still `names_product` pruning, which
reduces the *number* of `weighted_edit_similarity` calls
rather than the cost per call — and the two stack
multiplicatively. This plan should be pursued *with* the
pruning plan, not in lieu of it.

## Cost-folded DP

Mechanical note on the spec's "uniform across edit kinds" rule.

The current Python runs unit-cost Levenshtein opcodes and
applies `_edit_cost` post-hoc — meaning the alignment is
optimal under unit costs and the weighted cost is just a
re-score of an alignment chosen under a different model. With
cost-folded DP, each cell of Wagner-Fischer is parameterised
by the actual cost function, and the traceback yields an
alignment that is genuinely optimal under the spec's cost
table. Same DP skeleton; costs are the only thing that change.

This matters more once we adopt the "uniform across edit
kinds" rule: under unit-cost Levenshtein, delete-then-insert
costs the same as substitute (both 1), so retrofit re-scoring
mostly works out. Under the spec, delete `o` + insert `0`
should cost 0.7 (confusable), not `1.0 + 1.5 = 2.5` —
retrofit-after-unit-DP can't get this right.

## Test harness and Python baseline

Iterate the spec on a measurement loop, not on intuition.
Phase 1 has landed under `contrib/name_comparison/`; remaining
work is iterating the comparator.

#### Important caveat: the harness operates on degraded input

`cases.csv` carries only `name1` / `name2` strings — single
collapsed forms. Production matching in nomenklatura goes
through `followthemoney.names.entity_names`, which projects
the entity's structured properties (`firstName`, `lastName`,
`middleName`, `fatherName`, `motherName`, `title`,
`nameSuffix`, `weakAlias`) into `analyze_names`'s
`part_tags` argument. This gives parts authoritative
`GIVEN` / `FAMILY` / `MIDDLE` / `HONORIFIC` / `SUFFIX` /
`NICK` tags up-front, which:

- lets `align_person_name_order` canonicalise reliably
  ("Friedrich Hans" stays distinct from "Hans Friedrich"
  because tags differ),
- prevents cross-part-type pairing (a GIVEN token doesn't
  pair with a FAMILY token from the other side),
- amplifies `family_name_weight` correctly on FAMILY
  mismatches.

The harness deliberately does **not** reproduce this layer —
extending the schema to carry per-property tags is iteration
two in `cases.csv`, and is currently out of scope. As a
result, some PER-class failures the harness surfaces are
input-degradation artefacts, not residue-distance bugs.

Concretely, when interpreting failures: PER cases where
the failure mode is reorder-sensitive ("Friedrich Hans" vs
"Hans Friedrich"), family-name-mismatch ("Aung San Suu
Win" vs "Aung San Suu Kyi"), or middle-initial expansion
("Hans J Friedrich" vs "Hans Joachim Friedrich") are
known to be handled in production via the part-tag
projection. **Don't tune `compare_parts_orig` to fix these
on bare-string input** — it would over-optimise for the
harness against the wrong scenario. ORG cases (single-
token-near-typo, Roman/digit disagreement, geographic
qualifiers, location-extras) don't have an upstream-tag
escape hatch and are real iteration targets.

### `contrib/name_comparison/` (top-level, mirroring `nomenklatura/contrib/name_benchmark/`)

Self-contained harness with two CLI modes: run a named
comparator over `cases.csv` (storing per-case dumps for
diffing across iterations), or re-summarise a stored dump
without re-running.

Layout (as landed):

```
contrib/name_comparison/
├── cases.csv         # 310 labelled name pairs (source of truth)
├── run.py            # CLI: -c <name> to run, -s <run.csv> to summarise
├── run_data/         # timestamped per-case dumps, gitignored
└── README.md         # usage, schema, qsv recipes
```

`cases.csv` is hand-edited. Earlier iterations of this plan
imagined `convert_checks_yml.py` / `convert_yente_*.py`
scripts living in the directory — they've been retired.
The CSV is the canonical artifact; new sources are
brought in via one-shot scripts that get deleted after
ingestion. (Initial population pulled 226 cases from
nomenklatura's `checks.yml` and 84 from the
`tests/matching/` test cases.)

#### Case-file schema (v1)

Plain CSV. One pair per row. Single file, sources
distinguished by `case_group`.

| Column       | Required | Notes |
|--------------|----------|-------|
| `case_group` | yes      | Source/corpus tag: `nk_checks`, `nk_unit_tests`, future: `qarin_negatives`, `un_sc_positives`, `us_congress`. New sources add a new value; reports slice on it. |
| `case_id`    | yes      | Stable identifier within the group. `(case_group, case_id)` is the composite key. |
| `schema`     | yes      | FtM schema name (`Person`, `Organization`, `Thing`, `Vessel`, …). Drives `analyze_names`'s `NameTypeTag` when the comparator chooses to use it. |
| `name1`      | yes      | Query-side name. Single string. |
| `name2`      | yes      | Result-side name. |
| `is_match`   | yes      | Ground-truth label (`true`/`false`). |
| `category`   | optional | Free-text mutation/heuristic class. Used to slice the confusion matrix. Blank if unlabelled. |
| `notes`      | optional | Free-text human-readable comment. Survives in the per-case dump for analyst review. |

Multi-name alias bags are not supported — encode each
pairing as its own row. Per-case expected-score ranges are
out of scope for v1.

#### Iteration two: tagged name parts

Once v1 is bedded down, extend the schema to support
explicit name-part tagging for cases where the matcher input
is structured (well-tagged customer records — KYC at
onboarding). Likely shape: optional columns
`name1_first`, `name1_last`, `name1_middle`, `name1_father`,
… mirroring the FtM property set, with the harness
synthesising the unstructured `name` from them when needed
and passing tag hints into `analyze_names`. Out of scope for
phase 1; flagged so the v1 schema doesn't lock us out of it.

#### Comparator API

A comparator is `Callable[[str, str], float]` returning a
score in `[0, 1]`. Each comparator decides its own
pre-processing — whether to call `analyze_names`, how much
of the matcher pipeline (`pair_symbols`,
`align_person_name_order`, `tag_sort`) to invoke before the
distance computation. The harness only owns CSV IO,
threshold application, and reporting.

`run.py` keeps a `COMPARATORS` registry (`Dict[str,
Comparator]`); adding an iteration is one new function plus
one dict entry. The CLI exposes the registry's keys as the
`-c` argument's `choices`.

Cases where the underlying matcher would have flipped on
non-name signals (identifiers, DOB, country) will appear as
"name distance disagrees with overall verdict" rows. Tag
those via the `category` column up front
(`identifier_match`, `weak_name_strong_metadata`) so they
don't get mistaken for name-distance bugs.

#### Run mode (`-c`)

```bash
python contrib/name_comparison/run.py -c levenshtein
```

Runs the comparator over `cases.csv`, writes
`run_data/<comparator>-YYYYMMDD-HHMMSS.csv`, and prints the
summary unless `--quiet`. Each row in the dump:

```
case_group, case_id, schema, name1, name2, is_match,
category, notes, score, predicted_match, outcome
```

with `outcome ∈ {TP, FP, TN, FN}`. The dump preserves
`predicted_match`/`outcome` at run-time threshold, but the
summary mode re-derives them from `score` so changing
threshold doesn't require re-running.

#### Summarise mode (`-s`)

```bash
python contrib/name_comparison/run.py -s run_data/<file>.csv -t 0.85
```

Reads a stored run CSV, applies a (possibly different)
threshold to the `score` column, and prints the same
summary. Lets us walk the precision/recall trade-off curve
from one execution. Critical for the "score response curve"
work — we want to see how a single comparator's confusion
matrix shifts across the 0.6-0.9 threshold band, not just
at the 0.7 alert bar.

#### Reporting

- **Confusion matrix** overall, plus per-`case_group` and
  per-`category` slices. Per-category surfaces *which kind
  of name-distance edit* is regressing (e.g. an iteration
  improving `Word Reordering` but regressing `Initials Usage`).
- **F1, precision, recall, accuracy** per slice.
- **Top-N FPs and FNs by score margin**: the cases the
  harness is most-confidently-wrong about, ranked by how far
  past the threshold the score sat. Highest-leverage starting
  point for analyst review.

#### Diffing iterations

`qsv diff old_run.csv new_run.csv` surfaces the cases that
flipped between two iterations — the actual feedback signal
for spec changes. Combined with the per-case `notes` column
(test-source provenance for `nk_unit_tests` rows), the
diff tells you both *what* flipped and *why* it was added
to the test set.

### Baseline numbers (Levenshtein, threshold 0.7)

The naïve baseline — `levenshtein_similarity` on casefolded
strings, no analysis — is the floor the spec iterations need
to clear. As of phase-1 landing:

| Slice            | n   | F1     | Precision | Recall | Accuracy |
|------------------|----:|-------:|----------:|-------:|---------:|
| Overall          | 310 | 0.540  | 0.700     | 0.440  | 0.577    |
| `nk_checks`      | 226 | 0.512  | 0.667     | 0.416  | 0.562    |
| `nk_unit_tests`  |  84 | 0.610  | 0.781     | 0.500  | 0.619    |

Per-category strong (F1 = 1.0): single-side typos
(Alphanumeric Swap, Character Deletion / Repetition,
Common Misspelling, Fat Finger Typo, Phonetic Replacement,
Word Joining). Per-category weak (F1 = 0.0): everything
needing structural awareness — Word Reordering, Title
Addition, Nickname Usage, Initials Addition, Name
Duplication Removal, Digit↔Text Conversion, Character
Reversal, plus most cross-script variants.

The 0.0-scoring FN cluster reflects `levenshtein_similarity`'s
internal max-edits cap firing on long pairs — it returns 0
when the pair exceeds the budget, not the unbounded-distance
similarity. Not a baseline implementation flaw; it just shows
that "edit distance over raw strings" loses on the cases
where pre-processing (transliteration, org-class
normalisation, reordering) carries the load.

Re-thresholding from the same dump shows the trade-off shape:
at `t=0.85` precision climbs to 0.80, recall drops to 0.35;
F1 stays roughly the same (0.49). Industry's precision/recall
trade-off curve in microcosm — visible from a single run.

### `compare_parts_orig` prototype (in the harness)

The Python prototype residue function lives in
`contrib/name_comparison/comparators/compare_parts_orig.py`.
**The `_orig` suffix is intentional**: it marks this as the
original Python reference, and reserves the unsuffixed name
`compare_parts` for the eventual Rust port in
`rigour.names.compare_parts`. During phase 3 both
implementations live side-by-side in the harness, registered
as separate comparators (`compare_python` vs `compare_rust`),
so `qsv diff` between their per-case outputs is the parity
check.

Phase 2 (spec iteration) operates on `_orig`. Phase 3 (Rust
port) reuses `_orig`'s settled spec as the reference for the
Rust implementation.

Internal three-function decomposition inside `_orig`:

```python
def compare_parts_orig(qry, res) -> List[Comparison]:
    align = _align(qry, res)            # cost model
    clusters = _cluster(align)          # pairing rule
    return [_score(c, align) for c in clusters]
```

Iterating one spec decision means swapping one of the three
internal functions; the variant registers as a new comparator
in `COMPARATORS` under `compare_python_<variant>`
(e.g. `compare_python_geometric_mean`,
`compare_python_fraction_budget`). When the spec settles,
the variants collapse into one `compare_parts_orig` body
that becomes the reference for the Rust port.

The harness's `orchestration.py` wraps the residue function
into a `(name1, name2, schema) -> float` Comparator (via
`analyze_names` + `pair_symbols` + tag-sort +
`compare_parts_orig` + weight policies + aggregation) and
registers it as `compare_python`. The wrapper bridges the
harness's string-level interface to the part-level primitive
— keeping the primitive unaware of weights / threshold /
`Match`.

### Iteration loop

With phase 1 landed:

1. Pick one open spec decision (combination function, budget
   shape, pairing rule, stopword curve).
2. Implement variant — either a new comparator added to
   `COMPARATORS`, or a parameter on `compare_parts` once that
   exists.
3. `python run.py -c <variant>` to generate a stored dump.
4. `qsv diff` against the previous best run; review the
   flipped cases and the per-category report.
5. Decide: keep, revert, or iterate further.
6. When the spec settles, port `compare_parts` to Rust. The
   harness compares Python reference against Rust port for
   correctness, not against a moving target.

The harness is also the natural home for the FP-rate test
loop: feed the negative fixtures from
`yente/contrib/candidate_generation_benchmark/fixtures/`
through the harness as additional `case_group` rows in
`cases.csv` and report distinct numbers per group.

## Cost-table data

The cost model needs at least one reference table — the
visual/phonetic confusable pairs — and probably more reference
data over time (digit→letter equivalences, weight tweaks per
NameTypeTag, etc.). This lives as a **single shared YAML
resource** under rigour's resource tree, **read by both the
Rust port and the harness's Python prototype** so iteration
on the table happens in one place.

Resource path: `resources/names/compare.yml` — broader
scope than just SIMILAR_PAIRS so we can grow it without
adding files. Initial contents:

```yaml
similar_pairs:
  # Visual / phonetic confusables. The cost-folded DP
  # treats any pair listed here at the confusable cost
  # tier, regardless of substitute / insert+delete path.
  - ["0", "o"]
  - ["1", "i"]
  - ["1", "l"]
  - ["g", "9"]
  - ["q", "9"]
  - ["b", "6"]
  - ["5", "s"]
  - ["e", "i"]
  - ["o", "u"]
  - ["i", "j"]
  - ["i", "y"]
  - ["c", "k"]
  - ["n", "h"]
```

Tier-2 pattern from `arch-rust-core.md`:

- `genscripts/` reads `resources/names/compare.yml` and emits:
  - a Rust slice literal under
    `rust/src/generated/names_compare.rs` (sorted, for
    binary-search at lookup time)
  - a Python module under `rigour/data/names/compare.py`
    (mirror dict / set, used by the harness during phase 2
    while the Rust port doesn't exist yet)
- Both artifacts are committed; CI re-runs `make rust-data`
  on each PR and fails on diff.
- `make rust-data` regenerates everything when `compare.yml`
  changes. No manual sync.

This locks out the trap where the harness has its own copy
of the table that drifts from rigour's. One source of truth
from day one.

`is_stopword` is already in Rust (`text::stopwords`). Existing
accessor; both the harness and the eventual Rust port call it
directly.

## Division of work

A specific allocation of every concept in this design across
three layers, with the principle: **rigour gets one new
public symbol, the harness reproduces logic_v2-style
orchestration locally, nomenklatura's logic_v2 remains
untouched until migration**.

### Layer 1 — rigour (additive)

After the spec settles, **one new public symbol**:

```python
def compare_parts(
    qry: List[NamePart],
    res: List[NamePart],
) -> List[Comparison]:
    """Score residue alignment between two NamePart lists.

    Residue = parts that survived pruning and symbol pairing,
    already tag-sorted by the caller. The function aligns
    them via cost-folded edit distance, clusters parts by
    alignment connectivity, and returns one Comparison per
    cluster (paired or solo). Knows nothing about Match,
    weights, stopwords, family-name boost, extra-name
    penalty, or the alert threshold.
    """
```

`Comparison` is a small dataclass / pyclass:
`qps: List[NamePart]`, `rps: List[NamePart]`, `score: float`.
**No `weight` field** — weight is matcher policy.

The function owns three internal stages (decomposed in
the harness prototype, collapsed in the final Rust port):

1. **Alignment** — cost-folded Wagner-Fischer + traceback
   over the joined NamePart strings. Output is a list of
   edit operations + per-character ownership + per-pair
   overlap counts.
2. **Clustering** — group `(qry_part, res_part)` pairs into
   `Comparison` records. Spec rule: alignment-connectivity
   (≥1 equal-character step connects two parts), with
   transitive closure.
3. **Scoring** — per-cluster combination function over
   per-part costs, with the length-budget cap.

These are separate decisions but live behind one entry
point — the alignment determines what clustering can see;
clustering determines which costs go into scoring.
Splitting them across the FFI boundary would create two
round-trips for the matcher and inflate the public API
surface. Keep them in one call.

### Layer 1.5 — rigour primitives unchanged

Already in rigour, used by the harness as-is:

- `Name`, `NamePart`, `Symbol`, `NameTypeTag`, `NamePartTag`
- `analyze_names`
- `pair_symbols`
- `align_person_name_order`, `NamePart.tag_sort`
- `text.distance.*` (used by simpler comparators)
- `text.stopwords.is_stopword`

No changes needed during phase 2. `compare.yml` adds via
the `make rust-data` pipeline; it doesn't change Python
imports.

### Layer 2 — harness (`contrib/name_comparison/`)

Throwaway scaffolding that reproduces logic_v2's
orchestration in pure Python so we can evaluate end-to-end
behaviour from `(name1, name2)` strings to a final aggregate
score on `cases.csv`.

Layout:

```
contrib/name_comparison/
├── cases.csv
├── run.py                          # CLI + reporting
├── comparators/
│   ├── __init__.py                 # COMPARATORS registry
│   ├── policies.py                 # lifted matcher-policy constants
│   ├── orchestration.py            # match_name_symbolic-shape pipeline
│   ├── levenshtein.py              # current naïve baseline
│   ├── comparable.py               # analyze_names + comparable form + LD
│   └── compare_parts.py            # the future rigour primitive, prototyped
└── run_data/
```

**`policies.py`** — constants lifted verbatim from
nomenklatura:
- `SYM_SCORES`, `SYM_WEIGHTS` (per-`SymbolCategory` weights)
- `EXTRA_QUERY_NAME`, `EXTRA_RESULT_NAME`,
  `FAMILY_NAME_WEIGHT`, `FUZZY_CUTOFF_FACTOR` defaults
- `weight_extra_match` (the function that computes the
  extra-name bias)

`SIMILAR_PAIRS` is **not** in `policies.py` — read instead
from `rigour.data.names.compare` (the genscript-emitted
Python mirror of `compare.yml`). Single source of truth.

**`orchestration.py`** — a simplified `match_name_symbolic`
in ~80-120 lines:
1. `analyze_names` on each side using the row's `schema`.
2. `pair_symbols` to get edge-pairings.
3. For each pairing: build cluster records from edges
   (using `SYM_SCORES`/`SYM_WEIGHTS`); compute residue;
   tag-sort; hand residue to the comparator's residue
   function; apply weight policies (extra-name,
   family-name, stopword); aggregate.
4. Return the best aggregate score across pairings.

Takes the residue function as a parameter. Different
comparators plug different residue functions in without
each rewriting the pipeline.

**`compare_parts_orig.py`** — the Python prototype residue
function. The `_orig` suffix marks it as the original Python
reference; the unsuffixed name `compare_parts` is reserved
for the eventual Rust port (see *Naming during the porting
phase* below). Same signature and semantics as the eventual
rigour symbol; phase 2 iterates this file's body.

Internal three-function decomposition:

```python
def compare_parts_orig(qry, res) -> List[Comparison]:
    align = _align(qry, res)            # cost model lives here
    clusters = _cluster(align)          # pairing rule lives here
    return [_score(c, align) for c in clusters]
```

`compare_parts_orig` is a *function*, not a registered
comparator. The registered comparator is `compare_python`
(in `orchestration.py`) — the full pipeline that uses
`compare_parts_orig` as its residue function. Spec
iterations register variants in `COMPARATORS` under names
like `compare_python_geometric_mean`, each one wrapping a
sibling residue function (or a `compare_parts_orig` invoked
with different internal-stage choices).

**`comparators/__init__.py`** — the registry:
```python
COMPARATORS: Dict[str, Comparator] = {
    "levenshtein": levenshtein_baseline,
    "compare_python": compare_python,                 # default
    # added during phase 2 spec iteration:
    # "compare_python_geometric_mean": compare_python_v2,
    # "compare_python_fraction_budget": compare_python_v3,
    # added in phase 3 once the Rust port lands:
    # "compare_rust": compare_rust,
}

if _LOGICV2_AVAILABLE:
    COMPARATORS["logicv2"] = logicv2_baseline         # frozen reference
```

### Naming during the porting phase

Two namespaces in tension, intentionally kept distinct:

- **Residue function**: `compare_parts_orig` (Python
  prototype) → `compare_parts` (Rust port at
  `rigour.names.compare_parts`).
- **Comparator** (full pipeline registered in
  `COMPARATORS`): `compare_python` (uses Python residue) →
  `compare_rust` (uses Rust residue) added in phase 3
  alongside `compare_python`.

The orchestration is identical between `compare_python` and
`compare_rust` — only the residue function changes. Both
run on every harness invocation during phase 3; `qsv diff`
between their per-case outputs is the parity check.

Once the Rust port hits parity-within-tolerance on
`cases.csv`, `compare_parts_orig` retires (the Python
prototype is no longer load-bearing) and `compare_python`
also retires. `compare_rust` becomes the canonical
comparator. Until then, the Python prototype is the
reference for what the Rust port has to reproduce.

### Layer 3 — frozen logic_v2 reference (one-time)

To anchor iteration against current behaviour without
making the harness depend on nomenklatura, **run logic_v2
once** over `cases.csv` from inside nomenklatura
(`contrib/name_benchmark/`'s existing harness handles
this), dump the per-case results, and commit the CSV here
as `run_data/logicv2-frozen.csv`. The harness then
compares its iterations against three things: ground
truth (`is_match`), the previous iteration, and the
frozen logic_v2 baseline. Frozen file generated once, not
re-run during iteration.

### Layer 4 — nomenklatura (deferred to migration phase)

Untouched during phase 2. When the spec settles and the
Rust port lands:

- Replace `weighted_edit_similarity`'s body with a wrapper
  over `rigour.names.compare_parts`, assembling `Match`
  objects from the returned `Comparison`s.
- Drop `_opcodes`, `_edit_cost`, the local `SIMILAR_PAIRS`
  constant.
- `strict_levenshtein` unchanged — out of scope.
- Match class, match_name_symbolic orchestration,
  weight policies (`weight_extra_match`, `SYM_*` tables),
  `ScoringConfig` knobs — all stay.

The harness's `orchestration.py` and `policies.py` retire
or hang around as a regression cross-check. nomenklatura
keeps its own orchestration (which is the actual ship
path); the harness's copy is throwaway scaffolding.

### Trade-offs

**Cost:** harness duplicates ~120 lines of logic_v2's
orchestration plus the policy constants. During iteration
that's manageable — the duplicated code is read-only
matcher policy, frozen unless we explicitly change it for
an ablation. Drift from nomenklatura is detectable via the
frozen baseline diff.

**Benefit:** rigour's API surface is one function. No
`Match`, no weights, no thresholds, no `ScoringConfig`.
FFI boundary at port time is `Vec<NamePart>` in,
`Vec<Comparison>` out — minimal, no policy crossing the
boundary. nomenklatura's matcher.py changes by exactly one
function call swap. logic_v2 stays logic_v2's
responsibility.

**No backflow:** harness orchestration never migrates
back to nomenklatura. logic_v2's existing orchestration is
the ship path; the harness reproduces it solely to
evaluate end-to-end on cases.csv during iteration.

## Performance outliers — `pair_symbols` redundant spans on repeated tokens

Investigation triggered by the `Isa Bin Tarif Al Bin Ali` cases
in `cases.csv` running at ~2400 μs/call vs. a median of ~30 μs
across all comparators (compare_python, compare_rust, logicv2 —
the outlier is the *same* on all of them, ratio holds).

Stage timings on this case (after first-call warmup):

| Stage                       |    μs |
|-----------------------------|------:|
| `analyze_names` (both sides)|   ~20 |
| `pair_symbols`              | **~2000** |
| `compare_parts` (Rust, full)|   ~14 |

`pair_symbols` is the dominant cost. `compare_parts` is essentially
free even on this input — the Rust port does **not** help here
because residue distance isn't the bottleneck.

### Root cause: literal duplicate spans from `tagger.tag()` × `apply_phrase` interaction

The tagger emits **the same symbol multiple times on the same
NamePart instance** when a token appears more than once in the
name. Two interacting behaviours produce the duplication:

1. **`tagger.tag()`** (in `rust/src/names/tagger.rs`) iterates
   the AC `find_overlapping` matches and emits one
   `(phrase, symbol)` entry per `(text-position × symbol)`. For
   text `"isa bin tarif al bin ali"`, the AC fires on `"bin"`
   at two text positions; each fire iterates the symbol Vec
   attached to the AC pattern. With 8 symbols on the `"bin"`
   pattern (1 SYMBOL:BIN + 7 NAME:Qxxx from the person-names
   corpus), this yields 8 × 2 = **16 entries**, all with
   `phrase="bin"` and a duplicated `(phrase, symbol)` shape.
2. **`apply_phrase(phrase, symbol)`** (in
   `rust/src/names/name.rs`) walks the entire parts list and
   emits one span per occurrence of the phrase token sequence
   — independent of which text-position the AC match came
   from. Each call for `("bin", sym)` therefore emits a span on
   `bin@idx1` AND a span on `bin@idx4`.

Combined: 16 `(phrase, symbol)` entries × 2 spans per call =
**32 spans on `bin` alone**. All literal duplicates by
`(category, id, exact-NamePart-instance)`.

Surface effect on this case:

- `Isa Bin Tarif Al Bin Ali`: 43 spans total, 27 distinct by
  `(category, id, exact-NamePart-instance)` — 16 are pure
  duplicates.
- `Shaikh Isa Bin Tarif Al Bin Ali`: same shape on the
  candidate side, 45 spans.
- Naive `q-span × r-span` edge count for shared symbols: 139.
  `pair_symbols`' non-conflicting-coverage search enumerates
  this space.

Multiplicity formula: a token occurring N times in a name,
matched by an AC pattern with K symbols, produces **N² × K**
spans for that token. Tokens that occur once aren't affected.

### The fix — small, well-scoped

Dedupe `(phrase, symbol)` in `tagger.tag()`'s output. Two-line
change inside the iteration; `apply_phrase` already handles
emitting one span per token-instance correctly. Repro test:
the case above should drop from 43 spans → 27 spans on the
query side, the `pair_symbols` outlier should collapse from
~2000 µs to roughly the median.

### Implications

- The 2400 μs outlier is a `pair_symbols` issue, not a
  weighted-distance issue. Tuning `compare_parts` won't move
  it.
- The Rust port of `compare_parts` produces the same outlier
  pattern — both `compare_python` and `compare_rust` show the
  same 2400 μs median on this case. Any optimisation here lives
  in rigour's tagger (`rust/src/names/symbols.rs`,
  `tagger.rs`) or `pair_symbols` (`rust/src/names/pairing.rs`).

Recorded here for traceability — fix work belongs in
`rigour/rust/src/names/tagger.rs::Tagger::tag` and is not
blocking the weighted-distance / Rust port work.

## Caching

Current Python state:

- `_opcodes(qry_text, res_text)` is `@lru_cache(maxsize=MEMO_BATCH)`.
- `strict_levenshtein` is also `@lru_cache(maxsize=MEMO_BATCH)`.

Per `arch-rust-core.md`'s rule ("LRU caches at the Python
boundary, never inside Rust"), the cache should sit at the
Python wrapper:

```python
@lru_cache(maxsize=MEMO_BATCH)
def _aligned(qry_text: str, res_text: str) -> PartCosts: ...
```

But that requires keying on `qry_text + res_text`, not on the
`NamePart` lists. Two sub-questions:

1. **Cache key**: keying on the joined strings works only if we
   *also* recover part boundaries. The Rust function needs the
   `NamePart` list to assign costs to parts. So either:
   - The cache lives one level higher (cache the assembled
     `List[Match]`), keyed on the full `(qry_text, res_text,
     config_bias)` tuple. This matches what `match_name_symbolic`
     would actually want — the `Match` list is the contract.
   - Or we don't cache. Hit rate on `(qry_text, res_text)` is
     low: the literal-comparable short-circuit in
     `name_match` already absorbs exact equality; the
     `consolidate_names` pass dedupes near-duplicates. What
     reaches `weighted_edit_similarity` is the long tail.
2. **Hit rate measurement**: needed before claiming the cache is
   load-bearing. If hit rate is <10%, drop the cache (saves
   memory + the LRU lookup itself, which can rival sub-µs Rust
   calls).

The benchmark profile shows `_opcodes` at **99.96 % hit rate**
(154 cache misses across 390 k calls). That is the
high-end-of-plausible — `checks.yml` is a fixed test set with
heavy repetition. Production yente traffic against the
sanctions corpus will sit much lower. The measurement to take
on production traffic, not synthetic benchmarks: hit rate of
the equivalent string-keyed cache placed at the
`weighted_part_alignment` boundary.

Recommend: drop the cache initially; measure on production-
shaped traffic; reintroduce at the `Match`-list granularity
(or at the `PartCosts` boundary) if hit rate justifies it.

## Migration path

Five phases. Each one is a landable PR-shaped unit; later
phases gate on earlier ones.

1. **Harness + baseline (rigour, Python only).** ✅ **Landed in part.**
   - ✅ `contrib/name_comparison/` with `cases.csv`, `run.py`,
     `run_data/` (gitignored), README.
   - ✅ 226 rows from `nomenklatura/contrib/name_benchmark/checks.yml`
     (`case_group=nk_checks`); 84 rows from
     `nomenklatura/tests/matching/` (`case_group=nk_unit_tests`).
   - ✅ Two-mode CLI (`-c <comparator>` runs and dumps;
     `-s <run.csv>` re-summarises with re-thresholding).
     `COMPARATORS` registry pattern — adding an iteration
     is one new function plus one dict entry.
   - ✅ Naïve baseline (`levenshtein_baseline` over
     casefolded strings) measured: F1 = 0.540 overall at
     threshold 0.7. Per-category breakdown surfaces
     exactly the failure modes the design predicts
     (cross-script, reordering, abbreviation all at
     F1 = 0).
   - ✅ `comparators/policies.py` lifts SYM_SCORES,
     SYM_WEIGHTS, EXTRAS_WEIGHTS, weight_extra_match plus
     the four ScoringConfig defaults from logic_v2.
   - ✅ `comparators/orchestration.py` implements
     `compare_python` — the simplified `match_name_symbolic`
     shape calling `compare_parts_orig` for the residue.
     F1 = 0.885 on cases.csv.
   - ✅ `comparators/compare_parts_orig.py` — Python residue
     function with three-stage decomposition.
   - ✅ Frozen logic_v2 reference: `comparators/logicv2.py`
     wraps the real `nomenklatura.matching.logic_v2.LogicV2.compare`
     (soft-deps); `run.py --frozen` writes
     `run_data/logicv2-frozen.csv` (committed; gitignore
     exception on `*-frozen.csv`). F1 = 0.896. Diff against
     `compare_python` is 4 cases out of 310 (3 vessel-schema
     cases via `match_object_names`'s separate path, 1
     initials handling).
   - ✅ 258 LLM-generated synthetic adversarial cases added
     under `case_group=synth_companies` and
     `case_group=synth_people`. Generated interactively;
     subject to manual post-filtering. cases.csv → 568 rows.
     Updated scores at threshold 0.7: levenshtein F1=0.404,
     compare_python F1=0.707, logicv2 F1=0.715.
   - ✅ `resources/names/compare.yml` with the SIMILAR_PAIRS
     table; `genscripts/generate_names.py:generate_compare_file`
     emits `rust/data/names/compare.json` (bidirectional pairs,
     sorted, ready for `LazyLock<HashMap>` consumption from
     Rust). No Python emit — harness's Python prototype keeps
     an inline mirror until phase 3 retires it.
   - ✅ `contrib/name_comparison/perf.py` — apples-to-apples
     scoreboard combining accuracy (F1, P, R) with timing
     (μs mean / p50 / p95) per comparator, plus a top-N%
     slowest-cases leaderboard.
   - **Yente fixtures dropped from scope.** They run against
     real watchlist data, not (name1, name2, is_match) pairs;
     they don't fit the harness schema.

2. **Spec iteration on the harness.**
   - Implement still-open spec decisions (combination
     function, budget shape, pairing rule details, stopword
     curve) as variants of `compare_parts_orig`'s three
     internal functions (`_align`, `_cluster`, `_score`).
   - Each variant registers under `compare_python_<variant>`
     (e.g. `compare_python_geometric_mean`). Run via
     `python run.py -c compare_python_<variant>`, `qsv diff`
     against `compare_python` (current default) and
     `logicv2-frozen.csv` (frozen reference).
   - Phase 2 and phase 3 can run in **parallel**: phase 3
     ports current behaviour (not phase-2-settled behaviour),
     and spec iteration after the port lands can target
     either layer. Once a variant is chosen on the Python
     side, it gets re-ported to Rust to maintain parity.
     The compare_python ↔ compare_rust `qsv diff` is the
     parity gate at every step.
   - Acceptance: per-category gains where the failure mode
     is genuinely about the residue distance (ORG single-
     token-near-typo, Roman/digit disagreement, geographic
     qualifier on ORG, borderline-at-threshold). Failures
     covered by upstream part-tag projection in
     followthemoney (`Friedrich Hans` vs `Hans Friedrich`,
     family-name swaps on PER, middle-initial expansion)
     are explicitly **out of scope**.

3. **Rust port (rigour).** ✅ **First port landed; parity essentially closed.**
   - ✅ `rust/src/names/compare.rs` — cost-folded
     Wagner-Fischer with traceback, alignment-walk for
     per-part cost streams + per-pair overlap, 0.51-overlap
     clustering with transitive closure, product-of-side-
     similarities scoring with log-budget cap.
   - ✅ `Comparison` is a Rust pyclass (same convention as
     `Name`/`NamePart`/`Symbol`). FFI returns
     `Vec<Py<Comparison>>`.
   - ✅ Reads SIMILAR_PAIRS from `rust/data/names/compare.json`
     via `LazyLock<HashSet>`.
   - ✅ PyO3 binding (`rigour._core.compare_parts`),
     `_core.pyi` stub entries for `Comparison` +
     `compare_parts`. **No `rigour/names/compare.py` Python
     wrapper yet** — direct `_core.compare_parts` usage works
     fine for the harness; add the wrapper when the
     mkdocs-facing surface lands.
   - ✅ 7 Rust unit tests (cost-table lookup, edit-cost tiers,
     alignment basics, budget cap, transposition tie-break).
   - ✅ Harness adapter `comparators/compare_rust.py` registered
     as `compare_rust` in `COMPARATORS`. `orchestration.py`
     factored to take a `residue_fn` parameter; `compare_python`
     and `compare_rust` are sibling wrappers.
   - ✅ **Tie-break landed**: cost-folded Wagner-Fischer in
     Rust prefers one-sided edits (delete / insert) over
     substitution on cost-tied paths. Principled choice — a
     substitute step attributes cost to *both* sides, while
     delete attributes only qry and insert only res. The
     per-side budget cap in `_costs_similarity` cares about
     distribution, not totals; the distributive alignment
     respects that downstream accounting. Closes the
     transposition-class typo gap (Donlad/Donald,
     Olaf Schloz/Olaf Scholz, etc.).

   **Numbers post-tie-break-fix** at threshold 0.7
   (cases.csv n=569):

   | Comparator     |    F1 |     P |     R | μs mean | μs p50 | μs p95 |
   |----------------|------:|------:|------:|--------:|-------:|-------:|
   | compare_python | 0.707 | 0.590 | 0.883 |    39.7 |   28.0 |   61.4 |
   | compare_rust   | 0.708 | 0.589 | 0.888 |    35.1 |   23.3 |   53.9 |
   | logicv2        | 0.715 | 0.599 | 0.888 |    92.7 |   81.3 |  119.1 |

   **Parity status**: 2 case divergences out of 569. Same
   total error count as compare_python (150 each); the
   errors differ in pattern by 2 cases. Specifically:
     - `nk_checks/130` "Osama bin Laden" vs expanded form
       (is_match=true): **Rust correct (TP@0.732)**, Python
       wrong (FN@0.528). Rust's distributive alignment
       handles the long-form expansion better.
     - `nk_checks/218` "BAE Systems, Inc." vs "BAE
       Industries, Inc." (is_match=false): Rust wrong
       (FP@0.708), Python correct (TN@0.630). The 0.51-overlap
       clustering rule is sensitive to alignment-shape
       changes — the new tie-break produces fewer Equal-step
       chars between (systems, industries), so they don't
       cluster as a paired-but-zero-score record. Solo
       records (with extra-name penalty) drag the aggregate
       down less than one paired-zero record. Symptom of a
       fragile clustering rule, not a tie-break issue;
       phase-2 spec iteration territory.

   **Speed**: ~12% faster on mean, ~17% on p50, ~12% on p95
   vs compare_python. Modest because the orchestration
   (analyze_names, pair_symbols, weight policies, aggregate)
   is shared Python code; only the residue function differs.
   The big speedup pattern would require moving more
   orchestration into Rust — out of scope per the
   division-of-work principle.

   **Tentative location.** If the cost-folded DP later grows
   into a re-usable primitive over arbitrary char sequences,
   the alignment core may slide down to
   `rust/src/text/compare.rs` and `names/compare.rs` becomes
   the part-aware wrapper. Decide once spec iteration
   surfaces text-level reuse.

4. **Nomenklatura migration.**
   - Replace `weighted_edit_similarity`'s body with a wrapper
     over `rigour.names.compare.compare_parts`, assembling
     `Match` objects from the returned `Comparison`s.
   - Drop `_opcodes`, `_edit_cost`, `SIMILAR_PAIRS`.
   - `strict_levenshtein` is unchanged — out of scope.
   - Acceptance: `tests/matching/` passes (with re-pins
     where the spec drift legitimately changed an
     expectation), `checks.yml` confusion matrix
     equal-or-better, FP-rate fixtures equal-or-better.
   - **Adoption notes go in this plan**, not in code: target
     nomenklatura release timing is out of scope per session,
     but every step that lands gets a corresponding entry in
     the *Resolved* section so future readers can trace what
     shipped when.

5. **Production validation.**
   - `contrib/name_comparison/perf.py` (added in phase 1) for
     local Python-vs-Rust before/after on cases.csv.
   - Production-shaped run (yente or equivalent) when the
     migration lands; not part of this plan.
   - Cache decision based on production hit rate.

### Threshold target

The matcher is tuned to a **0.7 alert threshold** — that's a
fixed design target across all spec iterations, not a tuning
variable. As `_score` changes, the curve shape adapts to keep
0.7 as the place where TP/FP clusters separate. We don't hunt
for a "better" threshold from the data; we keep 0.7 and shape
the curve around it.

### Explicitly ignored failure modes

These show up in `cases.csv` failures but are out of scope:

- **Reverse-name cases** (`rimaldiV nituP` vs `Vladimir Putin`,
  `Vladimir nitPu` vs `Vladimir Putin`): not a realistic input
  shape outside artificial tests.
- **Western-convention reorder FPs** (`Friedrich Hans` vs
  `Hans Friedrich`): handled in production by part-tag
  projection from FtM `firstName`/`lastName` properties (see
  the *Important caveat* section above). Not a residue-
  distance bug.
- **Family-name-swap on PER** (`Aung San Suu Win` vs
  `Aung San Suu Kyi`, `Lula da Souza` vs `Lula da Silva`):
  same — covered by `family_name_weight` once parts are
  FAMILY-tagged via structured input.
- **Cross-script for non-latinizable scripts** (Khmer / Thai /
  Arabic / CJK ↔ Latin where `analyze_names` doesn't
  latinize): tagger / transliteration concern, lives in
  `rigour.text.translit` and `normality`, not here.

## Resolved

- **API in `NamePart` terms.** Generic strings+offsets shape
  rejected. Rigour speaks NamePart for names; the only
  consumer is a name matcher.
- **Scoring drift permitted.** Redesign, not port.
  Implementation freedom on the cost model and on the
  alignment-aggregation scheme.
- **Cost-folded DP, not faithful port.** The weighted cost
  function parameterises the DP directly; the alignment is
  optimal under the actual cost model.
- **`names_product` is in.** Pruning is the baseline; the
  primitive is designed for the input distribution that
  survives it.
- **Public rigour API, not productised.** Lives under
  `rigour.names.*` with a `_core.pyi` stub entry and a
  mkdocs page. Documented as a name-matcher utility, not a
  general-purpose string-distance primitive. logic_v2 is
  the primary consumer; other nomenklatura matchers may
  also import. Not pitched as semver-rigid like the general
  text primitives.
- **Match-identity / NamePart hashing.** NamePart hashes are
  stable and existing tests cover this; not a re-litigation
  point.
- **`Comparison` return type, not `List[Match]`.** Keeps
  `Match` assembly in nomenklatura. `Comparison(qps, rps,
  score)` — no `weight` field; weight is matcher policy.
- **Rigour returns clusters, not raw alignment.** Option 1
  in the alignment-vs-clustering trade-off. Both stages
  (alignment, clustering) live behind one `compare_parts`
  call. Splitting them across the FFI would inflate the
  public surface and add a round-trip; clustering is a
  name-distance concern, not a matcher concern, so it
  belongs with alignment.
- **Cost-table data: YAML resource, Rust-only emit.**
  `resources/names/compare.yml` (broader-scope name in case
  more reference data joins). `genscripts/generate_names.py:
  generate_compare_file` emits `rust/data/names/compare.json`
  for the Rust loader. **No Python emit** — the harness's
  Python prototype keeps an inline mirror until phase 3
  retires it; a shared Python artifact for a few-week
  prototype isn't worth the genscript complexity. Drift
  caught by the parity test in phase 3.
- **`Comparison` is a Rust pyclass.** Same convention as
  `Name`/`NamePart`/`Symbol`. FFI returns `Vec<Py<Comparison>>`;
  no Python dataclass version once phase 3 lands.
- **0.7 threshold is fixed.** Tune the score curve to keep
  TP/FP separation around 0.7; don't search for a better
  threshold from the data. Industry-typical alert tier
  starts at 75% similarity; matching that bar is the design
  target.
- **Phase 2 and phase 3 run in parallel.** First Rust port
  reproduces current `compare_parts_orig` behaviour, not
  phase-2-settled behaviour. Spec iteration after the port
  lands targets either layer; the parity gate catches
  divergence.
- **First Rust port is sketch quality, no optimisation.**
  Plain `O(NM)` Wagner-Fischer with traceback, no
  bit-parallelism, no caches, no FFI memoisation.
  Optimisation work is sequenced after spec settles —
  premature optimisation against an algorithm that may still
  shift makes for wasted effort.
- **DP tie-break: prefer one-sided edits (delete / insert)
  over substitution on cost-tied paths.** Substitution
  attributes cost to both sides simultaneously; delete and
  insert attribute only one side per step. Same total work,
  different per-side accounting. The per-side budget cap in
  `_costs_similarity` cares about distribution, not totals,
  so the distributive alignment respects that downstream
  accounting. Closes the transposition-class typo gap
  (Donlad/Donald, etc.) — without it Rust matched 12 fewer
  cases than Python on cases.csv.
- **Explicit out-of-scope failure modes.** Reverse-name
  cases, Western-convention reorder, family-name swap on
  PER, cross-script for non-latinizable scripts. Detail in
  the *Explicitly ignored failure modes* subsection of the
  Migration path.
- **Two-level naming distinguishes residue function from
  comparator.** Residue function: `compare_parts_orig`
  (Python prototype) → `compare_parts` (Rust port at
  `rigour.names.compare_parts`). Comparator (full pipeline
  registered in COMPARATORS): `compare_python` (uses
  Python residue) → `compare_rust` (uses Rust residue),
  both registered alongside in phase 3. The orchestration
  is identical; only the residue function changes. `qsv
  diff` between `compare_python` and `compare_rust` per-
  case outputs is the parity check. Once parity is met,
  both Python entries retire.
- **WeightTable shortcut rejected.** Rust `rapidfuzz`
  exposes `WeightTable` for per-edit-type weights only
  (fixed insert/delete/substitute scalars). Can't express
  "0.7 for SIMILAR_PAIRS, 1.5 for digits, 0.2 for SEP-drop"
  — those are character-pair-conditional, not edit-type-
  conditional.
- **Stopword weight stays Python.** Matcher policy. Lives
  in the harness's `policies.py` during iteration, in
  nomenklatura's logic_v2 long-term.
- **No backflow from harness to nomenklatura.** Harness
  orchestration is throwaway scaffolding; logic_v2's
  existing orchestration is the ship path. The migration
  swaps logic_v2's `weighted_edit_similarity` call for one
  to `rigour.names.compare_parts`; nothing else moves.

## Acceptance bar

Two-tier:

- **Correctness.**
  - `nomenklatura/contrib/name_benchmark/checks.yml` — overall
    confusion-matrix score should be comparable to the current
    Python implementation. Per-case drift is expected and
    fine; aggregate correctness must hold.
  - `nomenklatura/tests/matching/` — full pytest suite
    (`test_logic_v2_*.py` especially) passes. Some test
    expectations may need re-pinning to the new outputs;
    that's expected under the redesign premise but each
    re-pinned test should be defensible per the spec
    (still-open question A).
  - `yente/contrib/candidate_generation_benchmark/` —
    quantitative false-positive-rate test using synthetic
    `negatives_*` fixtures (generated from the qarin
    screening-fixtures pipeline) plus `positives_un_*` and
    `positives_us_congress` recall fixtures. logic-v2 column
    should not regress on FP rate or recall against the
    baseline.
- **Speed.**
  - `contrib/name_benchmark/performance.py` — local
    before/after on the same checks.
  - Production-shaped run (yente or equivalent) without the
    LRU artefact, to confirm the win generalises.

Sanctions context is recall-protective: a false negative is
worse than a false positive. Where the spec offers a margin,
err toward keeping borderline matches.

## Still open

These all gate on the harness from phase 1 of the migration
path. None of them is worth deciding speculatively — each is
one variant + a harness re-run away from a number.

- **Per-side score combination.** Product (current,
  punitive), geometric mean (softer), or length-weighted
  average (info-symmetric). Choice interacts directly with
  the 0.7 alert threshold on borderline pairs.
- **Length budget shape.** Log-of-`(len-2)` (current, magic
  base), fraction-of-length-capped (e.g. `min(len*0.25, 4)`),
  sqrt-based, or piecewise. Same "very short → off, sub-
  linear after" shape; legibility differs.
- **Confusable-pair table content.** Today's SIMILAR_PAIRS
  is visual-only (~13 entries). Whether to add phonetic-
  confusable rows, and whether the table varies by
  `NameTypeTag` — decide on harness evidence. Resource
  location is settled (`resources/names/compare.yml`); only
  the contents are open.
- **Stopword down-weight curve.** Linear-in-fraction,
  threshold-when-any, or exponential decay. Small in
  practice; harness-driven.
- **Clustering rule fragility.** The 0.51-overlap rule is
  sensitive to alignment-shape changes — when the alignment
  produces N+1 vs N Equal-step characters between two parts,
  the cluster either forms (paired-but-zero-score record,
  weight 1.0) or doesn't (two solo records with extra-name
  weights). The two outcomes drag the orchestration aggregate
  down by different amounts even though the underlying string
  similarity is comparable. The phase-3 BAE Systems / BAE
  Industries case is a concrete example. Replacing the
  threshold with alignment-connectivity (per the spec's
  Pairing rule section) should make this less fragile;
  iterate on the harness.
- **Cache or no cache.** Defer to production-shaped
  measurement; default no cache. Reintroduce at the
  `Comparison`-list granularity if hit rate justifies.

## Systematizing and tuning the magic numbers

The cost function and surrounding policy carry ~25 magic numbers
between them. They've accumulated organically and we don't have a
defensible argument for the specific values today's defaults take.
This section lays out an approach to (a) consolidating where those
numbers live so changing one is a one-line edit and (b) finding
better values empirically without overfitting.

### Inventory: two distinct layers, different homes

**Layer A — residue distance** (in `compare_parts`).
Shapes the `_align` / `_score` math directly:

| Constant | Today | Tunable? |
|---|---:|---|
| `_edit_cost` SIMILAR_PAIRS substitute | 0.7 | yes |
| `_edit_cost` SEP-on-one-side | 0.2 | yes |
| `_edit_cost` digit-mismatch | 1.5 | yes |
| `_edit_cost` default substitute / insert / delete | 1.0 | structural (the unit) |
| `_costs_similarity` log base | 2.35 | yes |
| `_costs_similarity` `len - 2` floor | (formula) | structural |
| `_cluster` overlap threshold | 0.51 | structural — *replace*, don't tune |
| Score combination function | product | structural — *replace*, don't tune |

3-4 tunable scalars. The "structural" entries aren't tuning
targets — changing them is spec replacement, registered as a new
COMPARATORS variant.

**Layer B — matcher policy** (in `policies.py`, lifted from
nomenklatura `magic.py` + `model.py`). Shapes the
`match_name_symbolic`-shape orchestration around the residue:

| Constant | Today | Notes |
|---|---:|---|
| `EXTRA_QUERY_NAME` | 0.8 | unmatched query parts |
| `EXTRA_RESULT_NAME` | 0.2 | unmatched result parts |
| `FAMILY_NAME_WEIGHT` | 1.3 | family-name boost |
| `FUZZY_CUTOFF_FACTOR` | 1.0 | bias on `_costs_similarity` budget |
| `SYM_SCORES` per category | 0.6–0.9 (8 values) | symbol-edge scores |
| `SYM_WEIGHTS` per category | 0.3–1.3 (7 values) | symbol-edge weights |
| `EXTRAS_WEIGHTS` per category | 0.7–1.3 (4 values) | one-sided symbol weight |
| Stopword down-weights | 0.5 / 0.7 | inside `weight_extra_match` |

~17 tunable scalars. **Not phase 2's job.** These are matcher
policy that nomenklatura owns long-term; they came from real
production tuning. Phase 2 tunes Layer A only, with Layer B
frozen at today's logic_v2 defaults. Phase 4 (nomenklatura
migration) is the place to revisit Layer B if needed.

### Systematization

**Layer A scalars → `resources/names/compare.yml`.** Today the
YAML holds only `similar_pairs:`. Extend to:

```yaml
similar_pairs:
  - ["0", "o"]
  ...

costs:
  similar_pair: 0.7
  sep_drop: 0.2
  digit_mismatch: 1.5
  default: 1.0           # the unit; changing it rescales everything

budget:
  log_base: 2.35
  short_token_floor: 2   # `len - N` floor; encodes "below N+1 chars, fuzzy off"
```

`genscripts/generate_names.py:generate_compare_file` extends to
emit these into `rust/data/names/compare.json` alongside the
pairs. Both the Python prototype and the Rust port read from the
compiled JSON via the same loader path. Changing a scalar = one
YAML edit, one `make rust-data`, one rebuild — single source of
truth.

This is materially better than today, where editing the digit
cost requires touching `compare_parts_orig.py` AND
`rust/src/names/compare.rs` and trusting they stay in sync.

**Layer B (matcher policy) stays in `policies.py`.** Don't move
it across the rigour/nomenklatura boundary just to enable
sweeping; sweep locally during phase 2 if needed and re-sync
back to nomenklatura's `magic.py` and `model.py` at migration.

**Structural choices stay in code, switchable via COMPARATORS.**
Combination function, cluster rule, budget shape — each is a
fundamentally different algorithm. Different values aren't
sweepable scalars; they're sibling registry entries
(`compare_python_geometric_mean`,
`compare_python_alignment_connectivity`, etc.).

### Tuning approach: coordinate descent on the harness

In increasing rigour:

1. **Make the knobs swappable in the Python prototype.**
   `compare_parts_orig` accepts overrides via kwargs (default =
   today's values, eventually loaded from the genscript-emitted
   data). The harness gets a `compare_python_costsweep` factory
   that registers a parameterised variant per swept value.
   Don't touch Rust yet — tuning happens on the Python prototype
   first, settled values re-port to Rust once.
2. **Build `contrib/name_comparison/sweep.py`.** Takes a
   parameter name and a value range, runs the harness for each,
   reports F1 + per-`case_group` breakdown + per-`category`
   breakdown per value. Tells you not just "best value" but
   "which kind of failure does each value affect."
3. **Coordinate descent.** One parameter at a time. Hold others
   fixed at defaults. Sweep, take the value that maximises F1
   under a recall-floor constraint. Lock. Move to next.
   Repeat until no parameter improves.
   ~3-4 parameters × ~5 sweep values = ~20 harness runs. Fast.
4. **Per-category constraint reporting.** Catch tunes that
   improve overall F1 by tanking one specific failure class
   (overfitting to common cases at the expense of rare-but-
   important ones). Reject any tune that drops a category's F1
   below its baseline.
5. **Re-port settled values.** Update `compare.yml`, regenerate
   the JSON, rebuild Rust, verify `compare_rust` parity with
   `compare_python` post-tune.

### Caveats

**Overfitting to `cases.csv`.** Our 569 cases have known biases:
`nk_checks` and `nk_unit_tests` are regression sets (biased
toward historically-broken cases); `synth_*` is LLM-generated
adversarial (skewed `is_match=false`). Tuning to maximise F1
here produces a function tuned to *this corpus*, not to general
name-distance behaviour. Two mitigations:

- **Hold out a partition during sweeps.** E.g. tune on
  `nk_checks + nk_unit_tests`, validate on `synth_*`. Drop any
  tune that improves training F1 but worsens validation F1.
  The synthetic set was generated independently of the cost
  function, so it functions as held-out data.
- **Constrain by per-category recall.** Recall-protective
  stance — sanctions context wants false negatives below false
  positives in cost.

**Don't tune Layer B in phase 2.** Those values came from real
production tuning at OpenSanctions. Moving them is a logic_v2
change with downstream impact on the matcher's calibration.

**The 0.7 alert threshold is fixed** (per Threshold target
above). Tune the score curve, not the threshold. If a tune
produces a distribution where 0.65 separates TP/FP better than
0.7 does, that's not a win — that's evidence the tune broke
calibration.

### Concrete next step

The plumbing PR (no behaviour change):

1. Extend `resources/names/compare.yml` with `costs:` and
   `budget:` tables.
2. Update genscript to emit them into
   `rust/data/names/compare.json`.
3. Refactor Python prototype: read from
   `rigour.data.names.compare` (or a small loader during the
   transition), accept kwargs overrides.
4. Refactor Rust port: read scalars from the JSON via a
   `LazyLock<CompareCosts>`-style struct, replace inline
   constants.
5. Verify zero behaviour change — same numbers as today.

Sweep harness lands as a follow-up. Tuning runs after that.

## Notes for the implementation

- **SEP choice.** Single space is fine because `comparable`
  forms are casefolded ASCII-or-script with whitespace
  squashed. If `comparable` ever admits literal spaces, the
  alignment-internal SEP needs to be a non-character (``
  or similar). Worth a defensive assertion at the boundary.
- **Char-iteration cost on long ORG strings.** `comparable`
  for some ORG names can hit 100+ chars. Plain DP is `O(NM)`
  cells; at 100×100 = 10 000 cells * ~1ns = 10 µs. Still well
  under per-pair budget. If profiling shows ORG names dominating,
  revisit option C (bit-parallel).
- **`Indel` as a model.** Substitution at cost 2 (delete +
  insert) is closer to the human notion of "edits" for some
  inputs. Worth considering as one of the cost-model
  alternatives during the spec discussion (open A) — under
  the redesign-not-port premise this is now a live option
  rather than an experiment.

## Related

- `plans/name-screening.md` — industry context on sanctions /
  KYC screening that drives the score-as-ranking framing,
  the confidence-cliff curve shape, and the two-scenario
  configurability requirement.
- `plans/arch-rust-core.md` — the rapidfuzz opcodes-gap open
  question this plan resolves.
- `plans/arch-name-pipeline.md` — `Name` / `NamePart` object
  graph; this primitive consumes `NamePart` instances.
- `plans/name-matcher-pruning.md` — the orthogonal pruning work
  that reduces the *number* of pairs reaching this primitive.
  Both are throughput levers; they multiply rather than
  compete.
- `nomenklatura/matching/logic_v2/names/distance.py` — the file
  to inline.
- `nomenklatura/matching/logic_v2/names/match.py:64` — the
  single call site of `weighted_edit_similarity`.
- `rust/src/text/distance.rs` — existing Rust-side Levenshtein
  primitives (distance + cutoff variants); this plan adds the
  alignment-recovering sibling under `rust/src/names/distance.rs`
  because it's part-aware, not a generic text primitive.
