---
description: Architecture of rigour.names.compare_parts — the residue-distance primitive a name matcher reaches for after symbol pairing has peeled off the parts it can explain by other means. Cost-folded Wagner-Fischer alignment, overlap-fraction clustering, product-of-side-similarities scoring with a length-dependent budget cap.
date: 2026-04-30
tags: [rigour, names, distance, compare-parts, residue, architecture]
---

# Name residue-distance architecture

`rigour.names.compare_parts` scores the alignment of two `NamePart`
lists. It's the Rust-backed primitive a name matcher reaches for after
upstream stages (symbol pairing, alias tagging, identifier matching)
have peeled off the parts they can explain by themselves and a residue
of unrecognised tokens remains. The residue is where typos,
transliteration drift, and surface-form variants live, and where a
fuzzy verdict has to come from string-level evidence.

For the surrounding name pipeline (`Name`/`NamePart`, `analyze_names`,
`pair_symbols`) see [arch-name-pipeline.md](arch-name-pipeline.md). For
Rust core conventions see [arch-rust-core.md](arch-rust-core.md).

## API shape

```python
from rigour.names import compare_parts, Comparison

def compare_parts(
    qry: list[NamePart],
    res: list[NamePart],
    fuzzy_tolerance: float = 1.0,
) -> list[Comparison]: ...

class Comparison:
    qps: tuple[NamePart, ...]
    rps: tuple[NamePart, ...]
    score: float
```

`Comparison` is a Rust pyclass (same convention as
`Name`/`NamePart`/`Symbol`) with a frozen `(qps, rps, score)` shape.
The function returns one `Comparison` per cluster — paired (both sides
non-empty) or solo (one side empty, the other a single part). Every
input `NamePart` appears in exactly one `Comparison`; identity is
preserved across the FFI so callers can look back into their own
metadata via `is`.

Implementation lives at `rust/src/names/compare.rs` with PyO3 binding
exposed as `rigour._core.compare_parts` and re-exported from the public
`rigour.names.compare` module.

## Where the primitive sits

The matcher does four sequential stages before residue distance ever
sees a token:

1. **Pruning** drops pairs with no plausible alignment path
   (`names_product` script-bridge / symbol-overlap filter, see
   `plans/name-matcher-pruning.md`).
2. **Symbol pairing** matches tokens the rigour tagger has labelled
   on both sides — person-name corpus hits, org-class fragments,
   numerics, ordinals. These score independently of string distance.
3. **Person-name reordering on the residue.** For PER, the tokens
   left over from step 2 are run through `align_person_name_order`;
   for ORG/ENT, `tag_sort` does the same job by tag.
4. **Residue distance.** What `compare_parts` does.

What this means for the input distribution:

- **Inputs are short and low-information.** Recognised tokens have
  been peeled off. What's left is the ambiguous tail.
- **Inputs are order-aligned.** Step 3 makes positional comparison
  meaningful — the first remaining query token corresponds to the
  first remaining result token at the type-tag level.
- **Inputs are script-comparable.** Step 1 guarantees a textual or
  symbolic bridge. The function isn't asked to score Thai vs Cyrillic.

The design below targets this distribution, not arbitrary token pairs.

## Score semantics

Per-cluster score is in `[0, 1]`. **The score is a ranking signal, not
a probability** — see `plans/name-screening.md` for industry context.

- `1.0` — these tokens are clearly the same.
- `0.7` — the alert-to-human bar; output above this means "worth a
  person looking at." Sits at the bottom of the industry-typical
  "urgent human review" band (75–89%).
- `0.0` — no evidence.

The function does not claim "score = P(match)" — it claims monotonicity
and a useful response curve.

Sanctions context is recall-protective: a false negative (missed
sanctions hit) is more costly than a false positive (human review).
The recall-protective rule applies to typos / transliterations /
aliases of the same legal entity, not to structurally different
sub-entities of the same brand. Sister/sub-entity pairs
(`Bowne of Atlanta` vs `Bowne of Boston`, `Banco Santander S.A.` vs
`Banco Santander Chile S.A.`, `Deutsche Bank AG` vs
`Deutsche Bank GmbH`) are non-matches — the matcher identifies
specific legal entities, not corporate hierarchies.

### Response curve

The score function produces a *confidence cliff*: most of the mass at
the extremes, fast transition through the mid-range. This is what makes
the industry-standard threshold banding (60 / 75 / 90) operationally
useful.

| Match quality                          | Target score |
|----------------------------------------|--------------|
| Exact / 1 typo in long token           | ≥ 0.95       |
| Plausible match (1–2 char ambiguity)   | 0.70 – 0.85  |
| Borderline (transliteration drift)     | 0.40 – 0.70  |
| Clear non-match                        | < 0.30       |

The empty middle is intentional. Per-side product (`q_sim · r_sim`)
produces this shape via punitive squashing — `0.99² ≈ 0.98`
(preserved), `0.7² ≈ 0.49` (collapsed). Replacement combination
functions must preserve the cliff or have a defensible reason not to.

## Configurability via `fuzzy_tolerance`

Two consumer scenarios — KYC at customer onboarding (lower threshold,
recall-leaning) and payment / transaction screening (higher threshold,
precision-leaning) — share the same scoring core. Differences are
expressed as `fuzzy_tolerance` on the budget cap, not as separate
scoring functions. Higher tolerance = more permissive (more edits
admitted before cliff); lower tolerance = stricter. Default `1.0`
matches industry-typical recall-protective tuning.

In nomenklatura `logic_v2`, `fuzzy_tolerance` is sourced from
`ScoringConfig.nm_fuzzy_cutoff_factor`.

## Symmetry

Default symmetric in `(qry, res)`. Asymmetry is permitted if a concrete
case justifies it but is not required by default. Returned-record
ordering is not load-bearing (downstream sorts before display).

## Completeness invariant

**Every input `NamePart` appears in exactly one returned `Comparison`.**
Either:

- in a paired record (with at least one partner from the other side), or
- as a solo record (one side empty, the other side a single `NamePart`).

No `NamePart` is silently dropped. This is what gives the matcher
orchestration a correct handle on extra-token penalties via
`extra_query_name` / `extra_result_name` weight policies.

## Cross-boundary character flow

Two flow patterns are first-class. Both work without special-casing:

1. **Token merge / split.** `vanderbilt` ↔ `van der bilt`. A lone SEP
   gained or lost on one side costs ~0.2 — almost free.
2. **Token interspersal.** `john smith` ↔ `rupert john walker smith`.
   Whole extra tokens flow into solo records without dragging down the
   matched tokens.

The alignment scores across token boundaries, not just within tokens.
Per-token pre-alignment with explicit merge/split rules was considered
and rejected — it doesn't handle interspersal cleanly.

## Cost model

The DP is parameterised by a uniform char-pair cost function. Cost
depends on the `(char_q, char_r)` pair, **not** on whether the DP
labels the step substitute, insert, or delete.

| Edit                                      | Cost  | Why |
|-------------------------------------------|-------|-----|
| Equal characters (incl. equal SEP)        | 0.0   | exact |
| Confusable pair (visual/phonetic table)   | 0.7   | typo / OCR / transliteration noise |
| SEP gained or lost on one side            | 0.2   | token merge or split |
| Default substitute / insert / delete      | 1.0   | character-level noise |
| Digit-involved mismatch (no confusable)   | 1.5   | digits identify specific things |

Notes:

- `fund 5` vs `fund 8` — digit-vs-digit-different lands at 1.5.
- `(5, s)`, `(0, o)`, `(1, l)` etc. take confusable cost (0.7), not
  the digit cost. **Confusable beats digit when both could fire.**
- Equal SEP is free (token boundary preserved on both sides).
- SEP-substitute-letter takes default cost 1.0; we don't distinguish
  "letter near a boundary" from "letter at position N."

Visual / phonetic confusable pairs live in `resources/names/compare.yml`
(committed YAML). The genscript emits `rust/data/names/compare.json`
with both directions pre-expanded so the lookup is a single hash probe.
Editing the table is one YAML edit + `make rust-data`.

The remaining scalars (`COST_*`, `BUDGET_LOG_BASE`, `BUDGET_SHORT_FLOOR`,
`CLUSTER_OVERLAP_MIN`) live as named constants at the top of
`rust/src/names/compare.rs`. Lifting them into the YAML resource is
[plumbing work](weighted-distance.md#magic-number-systematization)
deferred until a tuning sweep needs it.

## Cost-folded DP

Cost-folded Wagner-Fischer with traceback (in `align_chars`). Each cell
of the DP is parameterised by the actual cost function and the
traceback yields an alignment that is genuinely optimal under the cost
table — not a unit-cost alignment retrofit-scored after the fact.

This matters once we accept "uniform across edit kinds." Under
unit-cost Levenshtein, delete-then-insert costs the same as substitute
(both 1), so retrofit re-scoring mostly works out. Under our cost
model, delete `o` + insert `0` should cost 0.7 (confusable), not
`1.0 + 1.5 = 2.5` — retrofit-after-unit-DP can't get this right.

For typical name lengths (`comparable` forms 5–30 chars) the matrix is
~150–900 cells and runs in single-µs Rust. Bit-parallel alignment
(Hyyrö 2003) was considered and rejected: would shave nanoseconds off
work that's already free, and locks the DP into unit costs.

### DP tie-break: prefer one-sided edits over substitution

When a substitute path and an insert+delete path have equal cost in the
DP, the traceback picks the one-sided edits. Reason: a substitute
attributes cost to *both* sides simultaneously; insert attributes only
to res, delete only to qry. The downstream per-side budget cap in
`run_score` cares about distribution, not totals — concentrating cost
on one span via a substitute can fail the cap where the same total cost
distributed across sides would pass.

The transposition-class typo (`donlad` ↔ `donald`) is the canonical
case. Both `sub+sub` (cost 2.0, all on one span both sides) and
`del+match+ins` (cost 2.0, 1.0 to each side) are tied under the cost
function; the distributive path is the alignment a per-side scorer
genuinely wants.

## Pairing rule

Two `NamePart`s pair into the same cluster when the alignment matches
more than `CLUSTER_OVERLAP_MIN` (0.51) of the shorter part's characters
between them. Pairing is transitive: A↔B and B↔C produce one cluster
`{qps=[…A…], rps=[…B…C…]}`. The transitive closure handles token-split
cases like `vanderbilt` ↔ `[van, der, bilt]` cleanly — they fold into
one cluster instead of three near-misses.

The 0.51 threshold is a known fragility point. When the alignment
produces N+1 vs N equal-char steps between two parts, the cluster
either forms (paired-but-zero-score record, weight 1.0) or doesn't
(two solo records with extra-name weights). The two outcomes drag the
orchestration aggregate down by different amounts even though the
underlying string similarity is comparable.

Replacing the threshold with alignment-connectivity (≥1 equal-char
step connects two parts) is the spec direction; iteration is open.
Tracked in `weighted-distance.md`.

## Per-cluster score

For paired clusters: `costs_similarity(q_costs) * costs_similarity(r_costs)`
where `costs_similarity` is

```
effective_len = max(len(costs) - BUDGET_SHORT_FLOOR, 1)
max_cost = log_BUDGET_LOG_BASE(effective_len) * fuzzy_tolerance
if total_cost == 0:    return 1.0
if total_cost > max_cost:  return 0.0
return 1 - total_cost / len(costs)
```

Two design points:

- **Cliff, not curve.** Once total cost exceeds the length-dependent
  budget, the side scores zero. Below the cap, similarity is a clean
  linear walk-down. The non-linearity is in the cliff, not in the
  score curve, which keeps the math transparent.
- **Fail-closed on short tokens.** Tokens shorter than
  `BUDGET_SHORT_FLOOR` get budget zero — any non-zero edit fails the
  cap. Stops the matcher from over-firing on 2-char Chinese given
  names, vessel hull suffixes, isolated initials.

The product (rather than mean / min) is intentional: punitive in the
middle of the curve. A 99 % / 50 % pair scores 0.495, not 0.745 —
either side being noisy zeros the cluster quickly. Right shape for a
recall-protective alert threshold.

Solo clusters (one side empty) score 0.0 by construction — they
represent unmatched parts and have no pair-based similarity to compute.
The matcher's orchestration weights them via `extra_query_name` /
`extra_result_name` policies before aggregation.

## Determinism

Same inputs produce identical outputs. Returned-record ordering is a
deterministic function of input order — clusters surface in
`(qry_idx, res_idx)`-sorted order, with solos appended.

## Input contracts (assumed, not checked)

`analyze_names` guarantees, and `compare_parts` relies on:

- Every `NamePart` has a non-empty `comparable` (≥ 1 char).
- `comparable` is casefolded and whitespace-squashed.
- Tag ordering on inputs is canonicalised (PER via
  `align_person_name_order`, ORG via `tag_sort`).
- `comparable` does not contain literal SEP characters (single space).
  If it ever does, the alignment-internal SEP needs to move to a
  non-character.

The function does not re-validate.

## What the primitive deliberately doesn't do

- **`Match` assembly.** That's matcher policy — `weight`, `symbol`,
  `is_family_name`, the family-name boost, the extra-name penalty,
  the literal-equality override. All live in nomenklatura's
  `logic_v2.names.match`.
- **Stopword down-weighting.** Matcher policy. `is_stopword` lives in
  `rigour.text.stopwords` but the *decision to apply 0.7 weight to a
  stopword cluster* lives in nomenklatura's orchestration.
- **Symbol pairing or alias matching.** Upstream concerns. By the time
  `compare_parts` sees parts, those decisions are baked in.
- **Caching.** No internal cache. If a caller wants memoisation it
  belongs at the matcher's `Match`-list granularity, keyed on
  `(qry_text, res_text, fuzzy_tolerance)`.

## Out-of-scope failure modes

These show up in real corpora but are handled elsewhere:

- **Reverse-name cases** (`rimaldiV nituP` vs `Vladimir Putin`): not a
  realistic input shape outside artificial tests.
- **Western-convention reorder** (`Friedrich Hans` vs
  `Hans Friedrich`): handled in production by part-tag projection from
  FtM `firstName`/`lastName` properties via `analyze_names`'s
  `part_tags` argument. Not a residue-distance bug.
- **Family-name swap on PER** (`Aung San Suu Win` vs
  `Aung San Suu Kyi`): same — covered by `family_name_weight` once
  parts are FAMILY-tagged via structured input.
- **Cross-script for non-latinizable scripts** (Khmer / Thai /
  Arabic / CJK ↔ Latin where `analyze_names` doesn't latinize):
  tagger / transliteration concern, lives in `rigour.text.translit`
  and `normality`.

## Related

- [arch-name-pipeline.md](arch-name-pipeline.md) — `Name`/`NamePart`
  object graph, `analyze_names`, `pair_symbols`.
- [arch-rust-core.md](arch-rust-core.md) — Rust core conventions.
- [name-screening.md](name-screening.md) — industry context that
  drives the score-as-ranking framing and confidence-cliff curve.
- [weighted-distance.md](weighted-distance.md) — open spec questions,
  magic-number tuning approach, nomenklatura migration plan.
- [name-matcher-pruning.md](name-matcher-pruning.md) — orthogonal
  pruning that reduces the *number* of pairs reaching this primitive.
