---
description: Migrate nomenklatura's name-part weighted_edit_similarity onto rigour's Rust compare_parts primitive. Phases 1–3 (harness, spec, Rust port + productisation) have landed; phase 4 (nomenklatura migration), phase 5 (production validation), and the open spec / magic-number tuning are tracked here.
date: 2026-04-30
tags: [rigour, nomenklatura, names, distance, migration]
status: in-progress
---

# Weighted name-part distance — migration plan

Move the inner loop of nomenklatura's name-part fuzzy matcher
(`weighted_edit_similarity`) into rigour's Rust core, so the hot path
of `match_name_symbolic` doesn't iterate opcodes and characters in
Python on every surviving `(query_name, result_name)` pair.

The durable architecture of the resulting primitive lives in
[arch-name-distance.md](arch-name-distance.md). This document tracks
what's shipped vs. what's still open.

## Status

| Phase | Status | Notes |
|---|---|---|
| 1. Harness + Python baseline | ✅ shipped | `contrib/name_comparison/` with 813-row `cases.csv`, accuracy + perf runners, comparator registry. |
| 2. Spec iteration | ⚠ partial | One round (DP tie-break) shipped. Combination function, budget shape, clustering rule, stopword curve still open. |
| 3. Rust port + productisation | ✅ shipped | `rigour.names.compare_parts` + `Comparison`, mkdocs page, 15 Python unit tests, harness adapter. |
| 4. Nomenklatura migration | ☐ open | Replace `weighted_edit_similarity`'s body with a wrapper over `rigour.names.compare_parts`. |
| 5. Production validation | ☐ open | Yente-shaped run; cache decision based on production hit rate. |

## What landed

### Phase 1 — harness (`contrib/name_comparison/`)

- `cases.csv`: 813 labelled name pairs across 5 case_groups
  (`nk_checks`, `nk_unit_tests`, `synth_companies`,
  `synth_corp_positives`, `synth_people`). Schema: `case_group,
  case_id, schema, name1, name2, is_match, quality, category, notes`.
  Quality column (`STRONG` / `MEDIUM` / `WEAK`) drives per-tier
  reporting and the calibration monotonicity check.
- `run.py`: accuracy harness with confusion matrix, per-`case_group`
  and per-`category` slices, top-N FP/FN by score margin.
- `perf.py`: timing harness with apples-to-apples scoreboard (F1, P,
  R, μs mean / p50 / p95 / total ms) and slowest-case leaderboard.
- `comparators/` registry: `levenshtein`, `compare_python`,
  `compare_rust`, `logicv2` (frozen reference, soft-deps on
  nomenklatura).
- `policies.py`: lifted SYM_SCORES, SYM_WEIGHTS, EXTRAS_WEIGHTS,
  weight_extra_match plus the four ScoringConfig defaults from
  logic_v2.
- `orchestration.py`: simplified `match_name_symbolic`-shape pipeline
  parameterised on `residue_fn`, so `compare_python` and
  `compare_rust` are sibling wrappers around the same orchestration.

### Phase 2 — spec iteration (partial)

- **DP tie-break.** Cost-folded Wagner-Fischer prefers one-sided
  edits (delete / insert) over substitution on cost-tied paths.
  Closes the transposition-class typo gap — without it Rust matched
  12 fewer cases than Python on cases.csv. Detail in
  [arch-name-distance.md § DP tie-break](arch-name-distance.md#dp-tie-break-prefer-one-sided-edits-over-substitution).
- All other spec questions still [open](#open-spec-knobs).

### Phase 3 — Rust port + productisation

- `rust/src/names/compare.rs`: cost-folded Wagner-Fischer with
  traceback, alignment-walk for per-part cost streams + per-pair
  overlap, 0.51-overlap clustering with transitive closure,
  product-of-side-similarities scoring with log-budget cap.
- `Comparison` is a Rust pyclass with frozen `(qps, rps, score)`
  shape; FFI returns `Vec<Py<Comparison>>`.
- Reads SIMILAR_PAIRS from `rust/data/names/compare.json` via
  `LazyLock<HashSet>`. Source YAML at `resources/names/compare.yml`,
  emitted by `genscripts/generate_names.py:generate_compare_file`.
- 7 Rust unit tests (cost-table lookup, edit-cost tiers, alignment
  basics, budget cap, transposition tie-break).
- **Public surface**: `rigour/names/compare.py` re-exports
  `compare_parts` and `Comparison` from `_core`; both are reachable
  from `rigour.names`. mkdocs entry at `docs/names.md`.
- **Python tests**: 15 cases in `tests/names/test_compare.py`
  covering empty inputs, identical-pair → 1.0, fuzzy edit, budget
  cliff, confusable / digit cost tiers, fuzzy_tolerance scaling,
  short-token fail-closed, token merge cheap, score in [0, 1],
  object identity preserved, repr shape, public-module reachability.
- Harness adapter `comparators/compare_rust.py` registered in
  `COMPARATORS`; uses public `rigour.names.compare_parts` (not
  `_core`).

### Numbers post-productisation (cases.csv n=813, threshold 0.7)

| Comparator     |    F1 |     P |     R | μs mean | μs p50 | μs p95 | total ms |
|----------------|------:|------:|------:|--------:|-------:|-------:|---------:|
| compare_rust   | 0.790 | 0.758 | 0.824 |    32.6 |   26.6 |   71.2 |     26.5 |
| logicv2        | 0.789 | 0.762 | 0.819 |    88.5 |   84.0 |  134.5 |     72.0 |

**~2.7× faster end-to-end vs. logic_v2** at F1 parity (with the LRU on
`_opcodes` disabled in nomenklatura's `distance.py` — production-shape
measurement). Recall slightly higher on the Rust side, precision
slightly higher on logic_v2. Numbers track to ~3 fractional case
flips between the two.

## Still open

### Phase 4 — nomenklatura migration

The single change: replace
`nomenklatura/matching/logic_v2/names/distance.py:weighted_edit_similarity`'s
body with a wrapper over `rigour.names.compare_parts`, assembling
`Match` objects from the returned `Comparison`s. Drop `_opcodes`,
`_edit_cost`, the local `SIMILAR_PAIRS` constant.

What stays in nomenklatura:

- `Match` class (carries matcher-policy fields `weight`, `symbol`,
  `is_family_name`).
- `match_name_symbolic` orchestration in `match.py`.
- Weight policies: `weight_extra_match`, `SYM_*` tables,
  `FAMILY_NAME_WEIGHT`, the literal-equality override, the stopword
  down-weight.
- `ScoringConfig` knobs (`nm_fuzzy_cutoff_factor` flows through as
  `fuzzy_tolerance`).
- `strict_levenshtein` (used only by `match_object_names`, out of scope).

Acceptance:

- `nomenklatura/tests/matching/` passes. Some test expectations may
  need re-pinning under the redesign premise; each re-pinned test
  should be defensible per the spec.
- `nomenklatura/contrib/name_benchmark/checks.yml` confusion matrix
  comparable to current Python implementation. Per-case drift is
  expected; aggregate correctness must hold.
- `yente/contrib/candidate_generation_benchmark/` FP-rate fixtures
  equal-or-better.

### Open spec knobs

None of these is worth deciding speculatively — each is one variant
plus a harness re-run away from a number.

- **Per-side score combination.** Product (current, punitive),
  geometric mean (softer), or length-weighted average
  (info-symmetric). Choice interacts directly with the 0.7 alert
  threshold on borderline pairs.
- **Length budget shape.** Log-of-`(len-2)` (current, magic base
  2.35), fraction-of-length-capped, sqrt-based, or piecewise. Same
  "very short → off, sub-linear after" shape; legibility differs.
- **Confusable-pair table content.** Today's `similar_pairs` is
  visual-only (~13 entries). Whether to add phonetic-confusable rows,
  and whether the table varies by `NameTypeTag` — decide on harness
  evidence.
- **Stopword down-weight curve.** Linear-in-fraction,
  threshold-when-any, or exponential decay. Small in practice;
  harness-driven. See [issue #202](https://github.com/opensanctions/rigour/issues/202)
  for the Bashar-class particle case (extending the existing 0.7
  weight to fire when *either* side is a stopword).
- **Clustering rule fragility.** The 0.51-overlap rule is sensitive
  to alignment-shape changes — a paired-but-zero-score cluster vs.
  two solos with extra-name weights drag the orchestration aggregate
  down by different amounts even when underlying similarity is
  comparable. The phase-3 BAE Systems / BAE Industries case is a
  concrete example. Replacing the threshold with alignment-
  connectivity (≥1 equal-char step) per the spec's pairing rule
  should make this less fragile.

### Magic-number systematisation

The cost function carries ~25 magic numbers between the residue layer
(in `compare.rs`) and the matcher policy (in nomenklatura
`policies.py`). They've accumulated organically and we don't have a
defensible argument for the specific values today.

**Two layers, different homes:**

| Layer | Where | What | Tunable? |
|---|---|---|---|
| A — residue distance | `compare.rs` constants | `COST_*`, `BUDGET_LOG_BASE`, `BUDGET_SHORT_FLOOR`, `CLUSTER_OVERLAP_MIN` | 3–4 scalars; rest are structural |
| B — matcher policy | nomenklatura `magic.py` / `model.py` | `EXTRA_QUERY_NAME`, `EXTRA_RESULT_NAME`, `FAMILY_NAME_WEIGHT`, `SYM_SCORES`, `SYM_WEIGHTS`, `EXTRAS_WEIGHTS`, stopword weights | ~17 scalars; came from real production tuning |

**Plumbing PR (no behaviour change):** lift Layer A scalars from
`compare.rs` constants into `resources/names/compare.yml` under
`costs:` and `budget:` keys. Genscript emits them into
`rust/data/names/compare.json` alongside the pairs. `LazyLock<...>`
pulls them at startup. Single source of truth; editing a scalar
becomes one YAML edit + `make rust-data`.

**Tuning sweep:** `contrib/name_comparison/sweep.py` (not yet
written) — coordinate descent on Layer A scalars, holding Layer B
frozen. Per-`category` constraint reporting catches tunes that
improve overall F1 by tanking one specific failure class. Hold out
`synth_*` partition for validation against `nk_*` training.

Layer B is **not phase 2 or phase 4 territory.** Those values came
from real production tuning at OpenSanctions; moving them is a
separate logic_v2 calibration exercise.

### Phase 5 — production validation

- Yente-shaped run on the real watchlist corpus. The cache decision
  is the main open question: nomenklatura's `_opcodes` LRU sits at
  99.96% hit rate on `checks.yml` (heavy repetition) but production
  traffic is the long tail. Hit rate of an equivalent string-keyed
  cache placed at the `Match`-list granularity is the measurement
  to take.
- Default: no cache. Reintroduce only if production hit rate
  justifies it.

## Out-of-scope failure modes

These show up in `cases.csv` failures but are handled elsewhere or
deliberately left as known weaknesses; see
[arch-name-distance.md § Out-of-scope failure modes](arch-name-distance.md#out-of-scope-failure-modes)
for the durable list.

## Related

- [arch-name-distance.md](arch-name-distance.md) — durable architecture
  of the residue-distance primitive.
- [arch-name-pipeline.md](arch-name-pipeline.md) — `Name`/`NamePart`
  object graph, `analyze_names`, `pair_symbols`.
- [name-screening.md](name-screening.md) — industry context driving
  the score-as-ranking framing and confidence-cliff curve.
- [name-matcher-pruning.md](name-matcher-pruning.md) — orthogonal
  pruning that reduces the *number* of pairs reaching this primitive.
- `nomenklatura/matching/logic_v2/names/distance.py` — the file phase 4
  rewrites.
- `nomenklatura/matching/logic_v2/names/match.py:64` — the call site
  of `weighted_edit_similarity`.
