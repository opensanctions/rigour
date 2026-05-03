---
description: Migrate nomenklatura's name-part weighted_edit_similarity onto rigour's Rust compare_parts primitive. Phases 1–4 shipped; phase 5 (production validation) and the open spec / magic-number tuning are tracked here.
date: 2026-05-01
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
| 1. Harness + Python baseline | ✅ shipped | `nomenklatura/contrib/name_bench/` with 818-row `cases.csv`, accuracy + perf runners, comparator registry. (Originally landed in `rigour/contrib/name_comparison/`; moved to nomenklatura post-Phase-4.) |
| 2. Spec iteration | ⚠ partial | One round (DP tie-break) shipped. Combination function, budget shape, clustering rule, stopword curve still open. |
| 3. Rust port + productisation | ✅ shipped | `rigour.names.compare_parts` returning `Alignment`, mkdocs page, 17 Python unit tests. |
| 4. Nomenklatura migration | ✅ shipped | `weighted_edit_similarity` is now a thin wrapper over `rigour.names.compare_parts`; phase-3 shadow comparators (`compare_python`, `compare_rust`) retired. |
| 5. Production validation | ☐ open | Yente-shaped run; cache decision based on production hit rate. |

## What landed

### Phase 1 — harness (`nomenklatura/contrib/name_bench/`)

- `cases.csv`: 818 labelled name pairs across 5 case_groups
  (`nk_checks`, `nk_unit_tests`, `synth_companies`,
  `synth_corp_positives`, `synth_people`). Schema: `case_group,
  case_id, schema, name1, name2, is_match, quality, category, notes`.
  Quality column (`STRONG` / `MEDIUM` / `WEAK`) drives per-tier
  reporting and the calibration monotonicity check.
- `run.py`: accuracy harness with confusion matrix, per-`case_group`
  and per-`category` slices, top-N FP/FN by score margin.
- `perf.py`: timing harness with apples-to-apples scoreboard (F1, P,
  R, μs mean / p50 / p95 / total ms) and slowest-case leaderboard.
- `comparators/` registry: `levenshtein`, `logicv2`. The Phase-3
  spec-validation comparators (`compare_python`, `compare_rust`)
  and their backing Python prototype + lifted-policy modules were
  retired post-Phase-4 — `logicv2` covers the end-to-end behaviour
  they were validating.

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
- Returns the unified `Alignment` pyclass (qps, rps, symbol=None,
  score, qstr, rstr — see `arch-name-pipeline.md` § Alignment).
  FFI returns `Vec<Py<Alignment>>`.
- Reads SIMILAR_PAIRS from `rust/data/names/compare.json` via
  `LazyLock<HashSet>`. Source YAML at `resources/names/compare.yml`,
  emitted by `genscripts/generate_names.py:generate_compare_file`.
- 7 Rust unit tests (cost-table lookup, edit-cost tiers, alignment
  basics, budget cap, transposition tie-break).
- **Public surface**: `rigour/names/compare.py` re-exports
  `compare_parts` and `Alignment` from `_core`; both are reachable
  from `rigour.names`. mkdocs entry at `docs/names.md`.
- **Python tests**: 17 cases in `tests/names/test_compare.py`
  covering empty inputs, identical-pair → 1.0, fuzzy edit, budget
  cliff, confusable / digit cost tiers, fuzzy_tolerance scaling,
  short-token fail-closed, token merge cheap, score in [0, 1],
  object identity preserved, repr shape, public-module reachability,
  qstr/rstr caching, residue alignments carry symbol=None.

### Phase 4 — nomenklatura migration

`nomenklatura/matching/logic_v2/names/distance.py:weighted_edit_similarity`
is now a thin wrapper over `rigour.names.compare_parts`. Dropped:
`_opcodes`, `_edit_cost`, `_costs_similarity`, `SIMILAR_PAIRS`,
the cluster-build loop, `_PartCluster` scaffold (~120 lines).

Stayed in nomenklatura:

- Matcher-policy weights: `weight_extra_match`, `SYM_*` tables,
  `FAMILY_NAME_WEIGHT`, the literal-equality override, the stopword
  down-weight.
- `match_name_symbolic` orchestration in `match.py` — now mutates
  `Alignment.weight` / `Alignment.score` directly (rigour's
  `Alignment` is non-frozen post-Phase-4 with `Py<PyFloat>`-backed
  mutable score/weight; see `plans/alignment-type.md` history).
- `ScoringConfig` knobs (`nm_fuzzy_cutoff_factor` flows through as
  `fuzzy_tolerance`).
- `strict_levenshtein` (used only by `match_object_names`, out of scope).
- `is_family_name(alignment)` and `explain_alignment(alignment)` as
  free functions in `names/util.py` — matcher policy that stays
  with the matcher.

Parity check on swap: 4 outcome flips out of 818 cases on
`cases.csv` (none STRONG-tier). Two flips correct (`Osama bin
Laden` ↔ `Usāma bin Muhammad ibn Awad ibn Lādin` cross-script
recall, `MUHAMMAD AL-AHDAL` long-form FP rejected), two regress
(`BAE Systems`/`BAE Industries` and `MOHAMAD IQBAL ABDURRAHIM`/`…
ABDURRAHMAN`) — both driven by the spec change documented in
[arch-name-distance.md § DP tie-break](arch-name-distance.md#dp-tie-break-prefer-one-sided-edits-over-substitution)
and the fragility of the 0.51-overlap cluster threshold near a
single-character cliff. Net F1 unchanged at 0.795.

Perf on `nomenklatura/contrib/entity_bench/`:

| Run | Total | vs prev |
|---|---|---|
| `15_rig21baseline.perf` (rigour 2.1, pre-refactor) | 70.58s | — |
| `17_align.perf` (Alignment refactor) | 52.41s | −25.8% |
| `18_compare.perf` (compare_parts adopted) | 41.99s | −19.9% |

`weighted_edit_similarity` cumtime collapsed from 10.72s to 2.08s
(−81%); per-call cost from 27.2μs to 5.3μs (5.1× faster).

## Still open

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
- **Clustering rule fragility.** Two related issues:
  - The 0.51-overlap rule is sensitive to alignment-shape changes —
    a paired-but-zero-score cluster vs. two solos with extra-name
    weights drag the orchestration aggregate down by different
    amounts even when underlying similarity is comparable. The
    phase-3 BAE Systems / BAE Industries case is a concrete
    example. Replacing the threshold with alignment-connectivity
    (≥1 equal-char step) per the spec's pairing rule should make
    this less fragile.
  - The current clusterer joins a new `(qp, rp)` edge to whichever
    existing cluster already contains either side, but does not
    merge two existing clusters when a later edge bridges them
    (X-bridge). A part can end up referenced from two clusters in
    that case — rare under the 0.51 threshold (most parts have a
    single dominant counterpart) but a real invariant violation.
    The cost-stream layout means the duplicated part contributes
    its costs to both downstream cluster scores; downstream
    averaging tolerates it but it's not what the docstring promises.
    A union-find / DSU rewrite is the fix; landing it together with
    the connectivity-based pairing rule above is the natural shape.

### Magic-number systematisation

The cost function carries ~25 magic numbers between the residue layer
(in `compare.rs`) and the matcher policy (in nomenklatura
`magic.py`). They've accumulated organically and we don't have a
defensible argument for the specific values today.

**Two layers, different homes:**

| Layer | Where | What | Tunable? |
|---|---|---|---|
| A — residue distance | `CompareConfig` (frozen pyclass in `compare.rs`) | `cost_sep_drop`, `cost_confusable`, `cost_digit`, `budget_log_base`, `budget_short_floor`, `budget_tolerance`, `cluster_overlap_min` | 7 scalars; `COST_DEFAULT = 1.0` stays a compile-time unit anchor |
| B — matcher policy | nomenklatura `magic.py` / `model.py` | `EXTRA_QUERY_NAME`, `EXTRA_RESULT_NAME`, `FAMILY_NAME_WEIGHT`, `SYM_SCORES`, `SYM_WEIGHTS`, `EXTRAS_WEIGHTS`, stopword weights | ~17 scalars; came from real production tuning |

**Plumbing: `CompareConfig` (no behaviour change).** Lift Layer A
scalars out of `compare.rs` constants into a frozen pyclass passed
explicitly to `compare_parts`. Two motivations: parametric sweeping
becomes one Python kwarg instead of a recompile, and the existing
`fuzzy_tolerance` kwarg stops being a special-case singleton — it's
just one of seven knobs in the same struct.

```python
@dataclass(frozen=True)  # actual: #[pyclass(frozen)] in Rust
class CompareConfig:
    cost_sep_drop: float = 0.2     # was COST_SEP_DROP
    cost_confusable: float = 0.7   # was COST_CONFUSABLE
    cost_digit: float = 1.5        # was COST_DIGIT

    budget_log_base: float = 2.35  # was BUDGET_LOG_BASE
    budget_short_floor: float = 2.0  # was BUDGET_SHORT_FLOOR (usize → f64)
    budget_tolerance: float = 1.0  # was the fuzzy_tolerance kwarg

    cluster_overlap_min: float = 0.51  # was CLUSTER_OVERLAP_MIN

# new signature
compare_parts(qry, res, *, config=None) -> list[Alignment]
```

`COST_DEFAULT = 1.0` stays a compile-time constant — it's the unit
anchor for the cost-tier scale; sweeping it is just rescaling
everything else.

**Why frozen:** `CompareConfig` is immutable after construction.
Sweep scripts build a new instance per iteration
(`CompareConfig(cost_digit=1.4)`); the matcher caches one instance
per request. Two payoffs: `Py<CompareConfig>` is shareable across
threads with no runtime borrow checking, and the Rust side reads
`&CompareConfig` directly via PyO3 argument extraction — field
reads in the inner DP loop are native struct loads (no getter
dispatch, no boxing). Estimated per-call regression vs today's
const-folded constants: ~1–3% on `compare_parts` worst case,
<0.2% on full-matcher throughput. Within cases.csv noise.

**Default fast-path:** `config=None` resolves to a `LazyLock<CompareConfig>`
baked at startup. Callers that don't tune pay zero PyO3 boundary
cost (no borrow, no extraction) and get exactly today's behaviour.

**Caller pattern:** `nomenklatura.matching.logic_v2`'s
`weighted_edit_similarity` builds one `CompareConfig` from
`ScoringConfig` once at the top of `name_match` and threads it
down. `ScoringConfig` is invariant per matcher run, so reuse is
trivial — no per-`compare_parts` allocation.

**Budget rework still open.** The "very short → off, sub-linear
after" budget shape is up for revisit (see [Open spec knobs](#open-spec-knobs)).
When it lands, `budget_*` fields shift in/out of `CompareConfig`
without further API churn — that's the point of having the struct.

**Tuning sweep:** `nomenklatura/contrib/name_bench/sweep.py` (not
yet written) — coordinate descent on `CompareConfig` fields,
holding Layer B frozen. Per-`category` constraint reporting
catches tunes that improve overall F1 by tanking one specific
failure class. Hold out `synth_*` partition for validation
against `nk_*` training.

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
- [name-matcher-pruning.md](name-matcher-pruning.md) — orthogonal
  pruning that reduces the *number* of pairs reaching this primitive.
- `nomenklatura/matching/logic_v2/names/distance.py` — the file phase 4
  rewrites.
- `nomenklatura/matching/logic_v2/names/match.py:64` — the call site
  of `weighted_edit_similarity`.
