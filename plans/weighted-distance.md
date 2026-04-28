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

### `rigour/names/compare.py` (pending)

The Python implementation of the spec'd primitive. Not yet
written — currently the harness exercises only
`levenshtein_baseline` directly via the registry.

Once the spec iteration begins, `compare.py` will expose:

```python
def compare_parts(
    qry_parts: List[NamePart],
    res_parts: List[NamePart],
) -> List[Comparison]:
    """Score residue alignment between two NamePart lists.

    Each returned Comparison is either a paired record (qps
    and rps both non-empty) or a solo record (one side
    empty, the other a single part). Every input part
    appears in exactly one Comparison.
    """
```

`Comparison` is a small dataclass with `qps: List[NamePart]`,
`rps: List[NamePart]`, `score: float`, `weight: float`. No
dependency on `Match` — that stays in nomenklatura. The two
shapes are isomorphic; nomenklatura's wrapper is a one-liner
per record.

The harness wraps `compare_parts` in a `Comparator` adapter
(taking `(name1, name2) -> float` via `analyze_names` +
`pair_symbols` + tag-sort + `compare_parts` + score
aggregation) and registers it in `COMPARATORS`. The wrapper
is the bridge between the harness's string-level interface
and the part-level primitive — keeping the primitive
unaware of the harness, and the harness unaware of `Match`.

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

`SIMILAR_PAIRS` is small (~26 entries after the symmetric
expansion). Two natural homes:

- **Inline in Rust source.** A `phf_set!` or sorted `&[(char,
  char)]` literal in `rust/src/names/distance.rs`. Lookup is a
  binary-search or hash on each non-equal char pair.
- **YAML resource under `resources/names/`** with `genscripts/`
  emitting a Rust slice literal under `rust/src/generated/`.
  Same Tier-2 pattern as the script-range tables (see
  `arch-rust-core.md`).

The YAML approach is consistent with how rigour treats every
other linguistic resource. Recommend it.

`is_stopword` is already in Rust (`text::stopwords`). Existing
accessor; the Python-side wrapper just calls it.

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
   - **Pending:** yente fixtures (`qarin_negatives`,
     `un_sc_positives`, `us_congress`) added as additional
     `case_group` values in `cases.csv`. Population is a
     one-shot — no converter scripts retained.
   - **Pending:** `rigour/names/compare.py` implementing
     today's `weighted_edit_similarity` behaviour as
     `compare_parts`, returning `Comparison` records (no
     `Match` dependency). Adapter in `run.py` registers it
     as a comparator.

2. **Spec iteration on the harness (rigour, Python only).**
   - Implement the still-open spec decisions (combination
     function, budget shape, pairing-by-connectivity,
     uniform cost model, multi-token stopword) in
     `compare.py`.
   - Each iteration: run harness, diff confusion matrix and
     per-case scores against baseline, decide.
   - Acceptance: harness numbers stable, FP-rate / recall on
     the yente fixtures equal-or-better than baseline. Spec
     decisions move from "still open" to "resolved" in this
     plan as they land.

3. **Rust port (rigour).**
   - New module `rust/src/names/distance.rs` exposing the
     spec-finalised primitive. Cost-folded Wagner-Fischer +
     per-part cost accumulation + alignment-connectivity
     pairing.
   - Cost-table location decided per (D1, D2) above —
     inline Rust constants vs. YAML+genscript.
   - PyO3 binding + `_core.pyi` stub entry.
   - Rust-side unit tests for cost table, traceback, and
     the part-boundary cursor logic.
   - `rigour/names/compare.py` becomes a thin wrapper over
     the Rust call. Output equality with the Python baseline
     verified on the harness (within float tolerance).

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

5. **Production validation.**
   - `contrib/name_benchmark/performance.py` for local
     before/after.
   - Yente production-shaped run without the LRU artefact.
   - Cache decision based on production hit rate.

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
- **`PartCosts` (or equivalent struct) return type, not
  `List[Match]`.** Keeps `Match` assembly in nomenklatura.
- **WeightTable shortcut rejected.** Rust `rapidfuzz`
  exposes `WeightTable` for per-edit-type weights only
  (fixed insert/delete/substitute scalars). Can't express
  "0.7 for SIMILAR_PAIRS, 1.5 for digits, 0.2 for SEP-drop"
  — those are character-pair-conditional, not edit-type-
  conditional.
- **Stopword weight stays Python.** Matcher policy.

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
- **Confusable-pair table.** Today's SIMILAR_PAIRS is
  visual-only (~13 entries). Whether to add phonetic-
  confusable rows, and whether the table varies by
  `NameTypeTag` (D1) — both decide on harness evidence.
- **Stopword down-weight curve.** Linear-in-fraction,
  threshold-when-any, or exponential decay. Small in
  practice; harness-driven.
- **(D2) Cost-table location.** Inline Rust constants vs.
  YAML resource. ~13 entries don't earn the YAML+genscript
  pipeline; a multi-tag table might. Follows D1.
- **Cache or no cache.** Defer to production-shaped
  measurement; default no cache. Reintroduce at the
  `Comparison`-list granularity if hit rate justifies.

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
