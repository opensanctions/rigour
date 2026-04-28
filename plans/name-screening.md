---
description: Industry context for sanctions / KYC name screening. Score semantics, threshold tiers, FP-rate baselines, and the two consumer scenarios (customer onboarding vs. payment screening) that shape configurability requirements for the name-matching primitives.
date: 2026-04-28
tags: [rigour, nomenklatura, names, matching, screening, sanctions, kyc]
---

# Name screening: industry context

A reference memo capturing what mainstream sanctions and KYC
screening practice expects of a name-matching system. The
matching primitives in rigour and the policy layer in
nomenklatura's logic_v2 are designed to fit this picture; this
doc records the picture so future design decisions can reference
it without re-litigating from primary sources.

Not a design plan. Specific design plans
(`weighted-distance.md`, `name-matcher-pruning.md`) link here.

## The two consumer scenarios

The matcher serves two operationally distinct screening
contexts. Both run on the same scoring core, at different
threshold settings.

### Customer screening (KYC at onboarding, periodic refresh)

- **Input shape.** Structured customer record. `first_name`,
  `middle_name`, `last_name`, `date_of_birth`, `nationality`,
  `place_of_birth` all populated and reliably tagged.
- **Speed budget.** Seconds to minutes per record. Human
  review of any alert is expected.
- **Risk tolerance.** Recall-leaning. A missed sanctioned
  customer entering a relationship is a regulatory failure;
  an extra hour of analyst review is operational cost.
- **Typical threshold.** Industry guidance clusters at
  75–85% similarity. Lower (more permissive) than payment
  screening because human review is the safety net.

### Payment / transaction screening

- **Input shape.** Messy. SWIFT MT103 field 50 (orderer) is a
  4×35-char free-text blob, often truncated, often without
  name-part structure. ISO 20022 PACS.008 carries structured
  beneficiary fields but legacy MT103 traffic still dominates.
  Names may be missing punctuation, transliterated by an
  intermediate bank, or carry routing artefacts.
- **Speed budget.** Milliseconds. Decisions are largely
  automated; humans only review the alerts that actually fire.
- **Risk tolerance.** Precision-leaning. False positives
  delay or block settlement; the data quality is poor enough
  that aggressive fuzzy matching produces unmanageable noise.
- **Typical threshold.** Industry guidance clusters at
  88–95%. Higher (stricter) than KYC, with the caveat that
  some institutions push the *other* way (looser, to
  compensate for poor data) — the right direction is
  data-quality-dependent and not universally agreed.

### Implication: one scoring core, configurable bias

Don't fork the scoring math by scenario. The same primitive
(`compare_parts` per `weighted-distance.md`) produces the
same numeric output; the consumer chooses where to set the
threshold and how the budget cap is biased. logic_v2's
`nm_fuzzy_cutoff_factor` knob already serves this purpose;
keep that interface.

The two scenarios become two preset configs at the matcher
policy layer, not two scoring functions.

## Score is a ranking, not a probability

Industry practice uniformly treats a name-match score as a
tunable-threshold ranking signal, not a calibrated probability
of identity. We follow that convention.

- A score of `0.7` means "above the configured alert bar,"
  not "70% probability of identity."
- Monotonicity (better matches score higher) is the invariant
  we owe; calibration to a probability is not.
- This unblocks design choices that don't preserve
  probabilistic semantics — multiplicative side combination,
  log/sigmoid budget shapes, bias-as-multiplier.

Quotes from the sources:

- *"Scores function as a ranking mechanism — higher scores
  indicate stronger confidence in matches, with the threshold
  acting as the decision boundary."* (Babel Street)
- Verifex's published benchmark shows that even matches with
  95% confidence can be false positives. Score is **not** a
  P(match) prior.

## Industry threshold banding

Mainstream sanctions-screening systems bucket scores into
action tiers:

| Score band | Typical industry action          |
|------------|----------------------------------|
| 90–100%    | Auto-flag, immediate action      |
| 75–89%     | Urgent human review              |
| 60–74%     | Review only with corroboration   |
| <60%       | Auto-cleared                     |

logic_v2's `0.7` alert bar sits at the bottom of the "urgent
human review" band. The matcher's job is to push true
positives into the 0.85+ region and true negatives below
0.5, leaving 0.5–0.85 as a triage zone where humans (or
additional context — DOB, country, relationships) make the
call.

## Score-curve shape: the confidence cliff

For threshold banding to work, the score function must spend
its mass at the extremes and pass quickly through the
mid-range.

Target distribution shape:

| Match quality                          | Target score band |
|----------------------------------------|-------------------|
| Exact / 1 typo in a long token         | 0.95+             |
| Plausible match (1–2 char ambiguity)   | 0.70–0.85         |
| Borderline (transliteration drift, ambiguous tokens) | 0.40–0.70 |
| Clear non-match                        | <0.30             |

The empty middle is intentional. A linear `1 − cost/length`
function does **not** produce this shape; a non-linear
response — sigmoid, multiplicative product of per-side
similarities, or piecewise — does.

logic_v2's existing per-side product (`q_sim × r_sim`)
approximates the cliff: `0.99² ≈ 0.98` (preserved),
`0.7² ≈ 0.49` (collapsed), `0.5² ≈ 0.25` (collapsed harder).
That punitive squashing was load-bearing for the cliff
shape, even if it wasn't documented as such. Replacement
mechanisms must preserve the cliff or have a defensible
reason not to.

## Industry false-positive baseline

The industry runs hot. Reported FP rates on naïve fuzzy-name
screening:

- 90–95% across mainstream commercial systems (ACAMS, GBG
  Research, Sardine).
- Up to 99%+ on poorly-tuned or high-volume systems.
- ~90% of compliance-team analyst time spent reviewing
  false alerts.

Strong commercial offerings claim F1 in the 85–91% range;
benchmark leaders approach 95%+. F1 is the dominant
comparison metric (harmonic mean of precision and recall).

What this means for our work:

- The bar isn't "match academic name-matching accuracy" — it's
  "produce fewer false positives at equal recall than the
  FP-saturated baseline."
- A modest reduction in FP rate at preserved recall is
  meaningful operational impact, even if the absolute
  numbers stay high.
- The Federal Reserve's 2025 paper on LLMs in sanctions
  screening reports 92% FP reduction and 11% recall
  improvement vs. fuzzy baselines — note the framing,
  *across a range of thresholds*, not at one optimal point.

## Calibration is empirical

No source provides a theoretically-derived threshold.
FATF, the Federal Reserve, commercial vendors, and AML
educators all converge on the same prescription:

1. Tune against your data.
2. Document the rationale.
3. Monitor in production via alert volume, FP/TP rate,
   investigation outcomes.
4. Re-tune on each cycle.

Tuning is a regulator-facing artefact. Whatever value we
land on, the rationale has to be defensible to a supervisor.

For us, calibration concretely means:

- The harness in `rigour/contrib/name_comparison/` (per
  `weighted-distance.md`) is the calibration tool.
- `nomenklatura/contrib/name_benchmark/checks.yml` plus the
  qarin-generated negatives and UN-SC / US-Congress positive
  fixtures in
  `yente/contrib/candidate_generation_benchmark/fixtures/`
  are the calibration data.
- Threshold and bias choices land with documented before/
  after numbers, not derivations.

## Implications captured in design plans

The picture above drives specific choices recorded in
`weighted-distance.md`:

- **Score is in `[0, 1]` and explicitly *not* a
  probability.** Documented in the Spec section there.
- **Default symmetric in (qry, res); asymmetry available
  if needed.** KYC and payment screening have different data
  shapes; the function shouldn't bake either in.
- **Combination function preserves the cliff.** Per-side
  product is the current shape; harness-driven iteration
  validates whether alternatives (geometric mean, length-
  weighted average) are competitive without losing the
  cliff.
- **Budget cap is the bias knob.** `nm_fuzzy_cutoff_factor`
  multiplies into the cap; KYC and payment-screening
  configs differ on this number.
- **Recall-protective default.** Where the spec offers
  margin, err toward keeping borderline matches. Sanctions
  context — false negative > false positive.

## Out of scope here

- **Specific cost-table values.** Live in
  `weighted-distance.md`.
- **Threshold values per scenario.** Set by the consumer
  via `ScoringConfig`; logic_v2 ships defaults that
  downstream callers (yente, OpenSanctions internal tools,
  third parties) can override.
- **Full LogicV2 score-aggregation policy.** Lives in
  nomenklatura.
- **Recommendations on whether to deploy LLMs in the
  screening pipeline.** Out of scope; cited only for the
  empirical FP/recall figures.

## Related

- `plans/weighted-distance.md` — the residue distance
  primitive whose design this context informs.
- `plans/name-matcher-pruning.md` — the cross-product
  pruning that operates upstream of scoring.
- `plans/arch-name-pipeline.md` — the rigour name engine
  this matcher consumes.
- `nomenklatura/matching/logic_v2/names/match.py` — the
  matcher orchestration that combines rigour primitives
  with the policy layer.
- `nomenklatura/matching/types.py` — `ScoringConfig` and
  the `nm_*` knob set, including `nm_fuzzy_cutoff_factor`
  and the two scenarios' practical defaults.

## Sources

- [Sanctions screening trends 2026 — Alessa](https://alessa.com/blog/early-insights-from-the-2026-sanctions-screening-trends-survey/)
- [Verifex Sanctions Screening Accuracy Benchmark](https://verifex.dev/benchmark)
- [Babel Street — How to measure accuracy of name-matching technology](https://www.babelstreet.com/blog/how-to-measure-accuracy-of-name-matching-technology-and-what-to-know-before-you-buy)
- [Facctum — How to tune fuzzy matching thresholds](https://www.facctum.com/blog/how-to-tune-fuzzy-matching-thresholds)
- [Facctum — Customer vs. payment screening](https://www.facctum.com/comparisons/customer-screening-vs-payment-screening-key-differences-timing-and-integration)
- [Financial Crime Academy — Name vs. payment screening](https://financialcrimeacademy.org/name-screening-and-payment-screening/)
- [Financial Crime Academy — Fuzzy logic and matching algorithms](https://financialcrimeacademy.org/advanced-techniques-in-aml-compliance/)
- [SymphonyAI — Modernizing name screening](https://www.symphonyai.com/resources/blog/financial-services/name-screening/)
- [AML Analytics — Fuzzy matching validation guide, 2026](https://aml-analytics.com/2026/04/21/fuzzy-matching-aml-screening-validation-guide/)
- [Federal Reserve — Can LLMs improve sanctions screening? (FEDS 2025-092)](https://www.federalreserve.gov/econres/feds/can-llms-improve-sanctions-screening-in-the-financial-system-evidence-from-a-fuzzy-matching-assessment.htm)
- [scikit-learn — Probability calibration](https://scikit-learn.org/stable/modules/calibration.html)
