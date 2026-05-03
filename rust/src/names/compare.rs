//! Residue-distance scoring for two `NamePart` lists.
//!
//! Reach for [`py_compare_parts`] when a name matcher has already
//! peeled off the parts it can explain by other means (symbol
//! pairing, alias tagging, identifier hits) and is left with a
//! residue that needs a fuzzy-match verdict — typically misspellings,
//! transliteration drift, or surface-form variants of the same
//! token.
//!
//! The function returns one [`Alignment`] per cluster of aligned
//! parts (paired or solo). Every input part appears in exactly one
//! alignment, so a caller can sum / weight / threshold the result
//! without losing track of which inputs got accounted for. Returned
//! alignments carry `symbol = None` (residue distance is non-symbolic
//! by definition); the per-cluster `score` is the product of per-side
//! similarities, capped at zero by the length-dependent budget.
//!
//! Three concerns are folded into one call: how characters of
//! one side line up against the other (alignment), which parts
//! count as "talking about the same thing" (clustering), and
//! how confident we are per cluster (scoring). Splitting them
//! across the FFI would force callers to reconstruct context
//! they don't need; keeping them together also lets the cost
//! model parameterise the alignment directly, so the alignment
//! the matcher actually scores is the alignment a human-meaningful
//! cost function chose, not one chosen under unit costs and
//! retrofit-scored.
//!
//! Cost weights live in `resources/names/compare.yml` (visual /
//! phonetic confusables) and as constants in this file (digit,
//! SEP-drop, default substitute). They encode "what kinds of edit
//! count as evidence of typo vs. evidence of distinct entity":
//! confusable substitutes are cheap, digit mismatches are punitive,
//! SEP gain/loss is near-free (token-merge / token-split is a
//! common artifact of casual data entry).

use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use pyo3::prelude::*;
use serde::Deserialize;

use crate::names::alignment::Alignment;

use crate::names::part::NamePart;

/// Token boundary in the joined-name string the alignment runs over.
/// A single space works because `NamePart.comparable` is whitespace-
/// squashed casefold; if the contract ever drifts to admit literal
/// spaces inside a part's `comparable`, the SEP needs to move to a
/// non-character (e.g. `\u{0001}`) to stay unambiguous.
const SEP: char = ' ';

/// Default insert / delete / substitute cost. The unit anchor for
/// the cost-tier scale; everything else in [`CompareConfig`] is
/// calibrated relative to this. Sweeping it would just rescale the
/// rest, so it stays a compile-time constant.
const COST_DEFAULT: f64 = 1.0;

// --- Tunable scalars (CompareConfig) --------------------------------
//
// Seven scalars carved out of the residue-distance cost function so
// callers can pass alternatives without recompiling. The downstream
// budget cap is per-side, so the *gap* between cheap (cost_sep_drop)
// and expensive (cost_digit) edits is what determines whether a
// cluster squeaks under the cap or fails it. See
// `plans/weighted-distance.md` § Magic-number systematisation for the
// tuning context.

/// Tunable cost / budget / clustering scalars for [`py_compare_parts`].
///
/// Frozen by design: a sweep iteration constructs a fresh
/// `CompareConfig`, the matcher caches one per request. Mutability
/// would buy nothing (the values are read once per name pair) and
/// would cost a runtime borrow check on each Rust-side access.
///
/// The default values reproduce the constants this struct replaced;
/// `compare_parts(qry, res)` with no `config` argument is exactly
/// equivalent to the pre-`CompareConfig` call.
#[pyclass(frozen, from_py_object, module = "rigour._core")]
#[derive(Clone, Debug)]
pub struct CompareConfig {
    /// Token boundary lost or gained on one side. Token merge/split
    /// (`vanderbilt` ↔ `van der bilt`) is a common surface-form
    /// variant of the same name; charging it almost nothing keeps
    /// the alignment from refusing to bridge whitespace artifacts.
    #[pyo3(get)]
    pub cost_sep_drop: f64,

    /// Substitute between a confusable pair from
    /// `resources/names/compare.yml` (`0`/`o`, `1`/`l`, …). OCR /
    /// transliteration / homoglyph noise — the writer was probably
    /// aiming at the same character.
    #[pyo3(get)]
    pub cost_confusable: f64,

    /// Edit involving a digit on either side. Digits identify
    /// specific things — vintage years, vessel hull numbers, fund
    /// vintages — so a digit mismatch is evidence of a different
    /// entity, not a typo.
    #[pyo3(get)]
    pub cost_digit: f64,

    /// Logarithm base in the per-side cost-budget formula
    /// `log_budget_log_base(max(len - budget_short_floor, 1)) *
    /// budget_tolerance`. The base controls how aggressively the
    /// budget grows with token length — smaller base = faster
    /// growth = more permissive on long names.
    #[pyo3(get)]
    pub budget_log_base: f64,

    /// Short-token floor: tokens shorter than this contribute zero
    /// to the budget, so any non-zero edit fails the cap. This is
    /// the fail-closed property — the matcher refuses to fuzzy-
    /// match on 1-2 character tokens (vessel hull suffixes,
    /// isolated initials, 2-char Chinese given names) where typo /
    /// distinct-entity signal is too weak.
    #[pyo3(get)]
    pub budget_short_floor: f64,

    /// Multiplier on the per-side cost budget. Lower is stricter
    /// (less edit tolerated before a cluster scores zero); higher
    /// is more permissive. Callers tune this per scenario — KYC at
    /// onboarding runs more permissive than payment screening.
    #[pyo3(get)]
    pub budget_tolerance: f64,

    /// Overlap fraction (matched chars / shorter-side length) above
    /// which two parts pair into a cluster. A pair below this
    /// threshold surfaces as solo records — the matched-character
    /// evidence is too thin to claim the parts are talking about
    /// the same token. The 0.51 default (i.e. "more than half") is
    /// the lowest value where majority of the shorter token agrees.
    #[pyo3(get)]
    pub cluster_overlap_min: f64,
}

impl Default for CompareConfig {
    fn default() -> Self {
        Self {
            cost_sep_drop: 0.2,
            cost_confusable: 0.7,
            cost_digit: 1.5,
            budget_log_base: 2.35,
            budget_short_floor: 2.0,
            budget_tolerance: 1.0,
            cluster_overlap_min: 0.51,
        }
    }
}

#[pymethods]
impl CompareConfig {
    #[new]
    #[pyo3(signature = (
        cost_sep_drop = 0.2,
        cost_confusable = 0.7,
        cost_digit = 1.5,
        budget_log_base = 2.35,
        budget_short_floor = 2.0,
        budget_tolerance = 1.0,
        cluster_overlap_min = 0.51,
    ))]
    fn new(
        cost_sep_drop: f64,
        cost_confusable: f64,
        cost_digit: f64,
        budget_log_base: f64,
        budget_short_floor: f64,
        budget_tolerance: f64,
        cluster_overlap_min: f64,
    ) -> Self {
        Self {
            cost_sep_drop,
            cost_confusable,
            cost_digit,
            budget_log_base,
            budget_short_floor,
            budget_tolerance,
            cluster_overlap_min,
        }
    }

    fn __repr__(&self) -> String {
        format!(
            "CompareConfig(cost_sep_drop={}, cost_confusable={}, cost_digit={}, \
             budget_log_base={}, budget_short_floor={}, budget_tolerance={}, \
             cluster_overlap_min={})",
            self.cost_sep_drop,
            self.cost_confusable,
            self.cost_digit,
            self.budget_log_base,
            self.budget_short_floor,
            self.budget_tolerance,
            self.cluster_overlap_min,
        )
    }
}

/// Process-wide default `CompareConfig`, returned to the
/// `compare_parts(..., config=None)` fast path. One allocation at
/// startup; reads are zero-cost field accesses thereafter.
static DEFAULT_CONFIG: LazyLock<CompareConfig> = LazyLock::new(CompareConfig::default);

// --- Cost table -----------------------------------------------------

#[derive(Debug, Deserialize)]
struct CompareData {
    similar_pairs: Vec<[String; 2]>,
}

const COMPARE_JSON: &str = include_str!("../../data/names/compare.json");

/// Visually / phonetically confusable single-char pairs. Pre-expanded
/// to both directions at load time so the lookup is a single hash
/// probe — for `("0", "o")` the table contains both `('0', 'o')` and
/// `('o', '0')`.
static SIMILAR_PAIRS: LazyLock<HashSet<(char, char)>> = LazyLock::new(|| {
    let data: CompareData =
        serde_json::from_str(COMPARE_JSON).expect("rust/data/names/compare.json parses");
    let mut out = HashSet::with_capacity(data.similar_pairs.len());
    for [a, b] in data.similar_pairs {
        let ac = a.chars().next().expect("similar_pair char a present");
        let bc = b.chars().next().expect("similar_pair char b present");
        out.insert((ac, bc));
    }
    out
});

/// Cost of one edit step between `qc` (query side) and `rc`
/// (result side), keyed off the cost tiers in [`CompareConfig`].
///
/// Tier-selection is order-sensitive: SEP-drop checks come before
/// confusable lookup (so a SEP→non-SEP substitute falls through to
/// digit / default), and confusable beats digit (a `0`/`o` swap
/// gets `cost_confusable` even though `0` is a digit).
fn edit_cost(cfg: &CompareConfig, op: Op, qc: Option<char>, rc: Option<char>) -> f64 {
    if op == Op::Equal {
        return 0.0;
    }
    if qc == Some(SEP) && rc.is_none() {
        return cfg.cost_sep_drop;
    }
    if rc == Some(SEP) && qc.is_none() {
        return cfg.cost_sep_drop;
    }
    if let (Some(q), Some(r)) = (qc, rc) {
        if SIMILAR_PAIRS.contains(&(q, r)) {
            return cfg.cost_confusable;
        }
    }
    if matches!(qc, Some(c) if c.is_ascii_digit()) {
        return cfg.cost_digit;
    }
    if matches!(rc, Some(c) if c.is_ascii_digit()) {
        return cfg.cost_digit;
    }
    COST_DEFAULT
}

// --- Alignment ------------------------------------------------------

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Op {
    Equal,
    Replace,
    Delete,
    Insert,
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum BackPtr {
    None,
    Match,
    Substitute,
    Insert,
    Delete,
}

/// One step of the alignment as a `(qc, rc)` pair.
///
/// `qc=None` means the step is a result-only insert (no query
/// character consumed); `rc=None` means a query-only delete. Both
/// `Some` is either an `Equal` or a `Replace`.
#[derive(Clone, Debug)]
struct Step {
    op: Op,
    qc: Option<char>,
    rc: Option<char>,
}

/// Best-cost alignment between two character sequences under
/// [`edit_cost`].
///
/// The cost function is folded into the DP recurrence, so the path
/// returned is optimal under the actual scoring model — a substitute
/// of `0`/`o` (cost 0.7) genuinely beats a default substitute (cost
/// 1.0) at the cell level, not as a post-hoc re-score of a unit-cost
/// alignment. This matters when the cost tiers create real choices:
/// a sub-then-sub transposition costs 2.0 but doubles cost on a
/// single span; a del-then-match-then-ins around the same pair also
/// costs 2.0 but distributes 1.0 to each side. The tie-break (see
/// inline) prefers the distributive path.
fn align_chars(cfg: &CompareConfig, q_chars: &[char], r_chars: &[char]) -> Vec<Step> {
    let n = q_chars.len();
    let m = r_chars.len();

    // Cost matrix; (n+1) x (m+1).
    let mut cost: Vec<Vec<f64>> = vec![vec![0.0; m + 1]; n + 1];
    let mut back: Vec<Vec<BackPtr>> = vec![vec![BackPtr::None; m + 1]; n + 1];

    for i in 1..=n {
        cost[i][0] = cost[i - 1][0] + edit_cost(cfg, Op::Delete, Some(q_chars[i - 1]), None);
        back[i][0] = BackPtr::Delete;
    }
    for j in 1..=m {
        cost[0][j] = cost[0][j - 1] + edit_cost(cfg, Op::Insert, None, Some(r_chars[j - 1]));
        back[0][j] = BackPtr::Insert;
    }

    for i in 1..=n {
        for j in 1..=m {
            let qc = q_chars[i - 1];
            let rc = r_chars[j - 1];

            // Match (equal chars, cost 0)
            let match_cost = if qc == rc {
                Some(cost[i - 1][j - 1])
            } else {
                None
            };
            // Substitute (replace)
            let sub_cost = cost[i - 1][j - 1] + edit_cost(cfg, Op::Replace, Some(qc), Some(rc));
            // Delete from query
            let del_cost = cost[i - 1][j] + edit_cost(cfg, Op::Delete, Some(qc), None);
            // Insert from result
            let ins_cost = cost[i][j - 1] + edit_cost(cfg, Op::Insert, None, Some(rc));

            // Tie-break on cost: prefer one-sided edits (delete /
            // insert) over substitution. Substitution attributes
            // cost to both sides simultaneously; delete attributes
            // only to qry, insert only to res. The downstream
            // budget cap is per-side, so concentrating cost on one
            // span with a substitute can fail the cap where the
            // same total cost split across sides would pass. The
            // distributive path is the alignment a per-side scorer
            // genuinely wants.
            let mut best = sub_cost;
            let mut bp = BackPtr::Substitute;
            if let Some(mc) = match_cost {
                if mc <= best {
                    best = mc;
                    bp = BackPtr::Match;
                }
            }
            if del_cost <= best {
                best = del_cost;
                bp = BackPtr::Delete;
            }
            if ins_cost <= best {
                best = ins_cost;
                bp = BackPtr::Insert;
            }
            cost[i][j] = best;
            back[i][j] = bp;
        }
    }

    // Traceback
    let mut steps: Vec<Step> = Vec::new();
    let (mut i, mut j) = (n, m);
    while i > 0 || j > 0 {
        let bp = back[i][j];
        match bp {
            BackPtr::Match => {
                steps.push(Step {
                    op: Op::Equal,
                    qc: Some(q_chars[i - 1]),
                    rc: Some(r_chars[j - 1]),
                });
                i -= 1;
                j -= 1;
            }
            BackPtr::Substitute => {
                steps.push(Step {
                    op: Op::Replace,
                    qc: Some(q_chars[i - 1]),
                    rc: Some(r_chars[j - 1]),
                });
                i -= 1;
                j -= 1;
            }
            BackPtr::Delete => {
                steps.push(Step {
                    op: Op::Delete,
                    qc: Some(q_chars[i - 1]),
                    rc: None,
                });
                i -= 1;
            }
            BackPtr::Insert => {
                steps.push(Step {
                    op: Op::Insert,
                    qc: None,
                    rc: Some(r_chars[j - 1]),
                });
                j -= 1;
            }
            BackPtr::None => {
                // Should only fire at (0, 0). Guard against infinite loop.
                break;
            }
        }
    }
    steps.reverse();
    steps
}

// --- Alignment → per-part cost streams + per-pair overlaps ---------

/// Two views of an alignment that downstream stages need.
///
/// `qry_costs[i]` / `res_costs[i]` are the per-character cost streams
/// attributed to part `i` on each side — used by the scorer to compute
/// per-side similarity. `overlaps` counts `Equal`-step matches between
/// each `(q_part, r_part)` pair — used by the clusterer to decide
/// which parts pair up.
struct AlignmentData {
    qry_costs: Vec<Vec<f64>>,
    res_costs: Vec<Vec<f64>>,
    overlaps: HashMap<(usize, usize), u32>,
}

/// Run the DP over the SEP-joined strings and accumulate per-part
/// cost streams + per-pair overlap counts as we walk the alignment.
///
/// The walk advances a cursor on each side every time it consumes a
/// SEP — which is how cost / overlap end up attributed to the right
/// part instead of bleeding across token boundaries.
fn run_align(
    cfg: &CompareConfig,
    qry_comparable: &[String],
    res_comparable: &[String],
) -> AlignmentData {
    let n_q = qry_comparable.len();
    let n_r = res_comparable.len();
    let mut qry_costs: Vec<Vec<f64>> = vec![Vec::new(); n_q];
    let mut res_costs: Vec<Vec<f64>> = vec![Vec::new(); n_r];
    let mut overlaps: HashMap<(usize, usize), u32> = HashMap::new();

    if n_q == 0 || n_r == 0 {
        return AlignmentData {
            qry_costs,
            res_costs,
            overlaps,
        };
    }

    // Build the SEP-joined char vectors for both sides.
    let q_text: String = qry_comparable.join(&SEP.to_string());
    let r_text: String = res_comparable.join(&SEP.to_string());
    let q_chars: Vec<char> = q_text.chars().collect();
    let r_chars: Vec<char> = r_text.chars().collect();

    let steps = align_chars(cfg, &q_chars, &r_chars);

    // Walk the alignment, advancing part-cursors on each SEP.
    let mut qry_idx: usize = 0;
    let mut res_idx: usize = 0;

    for step in &steps {
        let qc = step.qc;
        let rc = step.rc;
        if step.op == Op::Equal
            && qc.is_some()
            && qc != Some(SEP)
            && rc.is_some()
            && rc != Some(SEP)
        {
            *overlaps.entry((qry_idx, res_idx)).or_insert(0) += 1;
        }
        let cost = edit_cost(cfg, step.op, qc, rc);
        if let Some(c) = qc {
            qry_costs[qry_idx].push(cost);
            if c == SEP && qry_idx + 1 < n_q {
                qry_idx += 1;
            }
        }
        if let Some(c) = rc {
            res_costs[res_idx].push(cost);
            if c == SEP && res_idx + 1 < n_r {
                res_idx += 1;
            }
        }
    }

    AlignmentData {
        qry_costs,
        res_costs,
        overlaps,
    }
}

// --- Clustering ----------------------------------------------------

/// Indices of parts that align with each other.
///
/// One side empty means "this part has no counterpart" — the part
/// surfaces in the output as a solo record so callers know it went
/// unaccounted-for. Both sides non-empty means "these parts are
/// talking about the same thing" (subject to the matcher's notion
/// of *thing*).
struct Cluster {
    qps: Vec<usize>,
    rps: Vec<usize>,
}

/// Pair query/result parts into clusters by overlap-fraction
/// threshold, with shared-vertex merging.
///
/// A pair `(qp, rp)` joins a cluster when the alignment matched more
/// than `cfg.cluster_overlap_min` of the shorter part's characters
/// between them — strong enough overlap that they're plausibly the
/// same token, ignoring noise. Eligible pairs are processed in
/// sorted order; each pair joins the cluster that already contains
/// either side, or creates a fresh cluster if neither side has been
/// seen. This handles star-shaped patterns (e.g. `vanderbilt` ↔
/// `[van, der, bilt]` — one query part bound to three result parts)
/// and chain-shaped patterns (`q0`↔`r0`, `q0`↔`r1`, `q1`↔`r1`)
/// cleanly: each new edge shares a vertex with the growing cluster.
///
/// The shared-vertex merge would mishandle an "X-bridge" where two
/// already-existing clusters get connected by a later edge that
/// shares no vertex with either's original. That case is
/// structurally unreachable here: `align.overlaps` is built by a
/// monotone DP walk, so its keys form a non-decreasing path in
/// `(qp, rp)`-space and can't contain the cross pattern an X-bridge
/// requires. If the DP ever stops being monotone — or the threshold
/// drops to admit many more edges per the connectivity-rule
/// proposal in `plans/weighted-distance.md` — replace the loop with
/// a part-id DSU.
///
/// Parts that no overlap pair clears the threshold for surface as
/// solo clusters at the end.
fn run_cluster(
    cfg: &CompareConfig,
    align: &AlignmentData,
    qry_lengths: &[usize],
    res_lengths: &[usize],
    n_q: usize,
    n_r: usize,
) -> Vec<Cluster> {
    // qry-side part index -> cluster index in `clusters`.
    let mut q_to_cluster: HashMap<usize, usize> = HashMap::new();
    let mut r_to_cluster: HashMap<usize, usize> = HashMap::new();
    let mut clusters: Vec<Cluster> = Vec::new();

    // Iterate overlap pairs in (q_idx, r_idx) order so the cluster
    // identity assigned to each part is deterministic — when
    // multiple pairs would compete to claim a part, the
    // earliest-indexed pair wins.
    let mut entries: Vec<((usize, usize), u32)> =
        align.overlaps.iter().map(|(&k, &v)| (k, v)).collect();
    entries.sort_by_key(|(k, _)| *k);

    for ((qp, rp), overlap) in entries {
        let q_len = qry_lengths[qp];
        let r_len = res_lengths[rp];
        let min_len = q_len.min(r_len);
        if min_len == 0 {
            continue;
        }
        let frac = overlap as f64 / min_len as f64;
        if frac > cfg.cluster_overlap_min {
            // Find existing cluster for either side, else create one.
            let cluster_idx = match (q_to_cluster.get(&qp), r_to_cluster.get(&rp)) {
                (Some(&i), _) => i,
                (None, Some(&i)) => i,
                (None, None) => {
                    clusters.push(Cluster {
                        qps: Vec::new(),
                        rps: Vec::new(),
                    });
                    clusters.len() - 1
                }
            };
            let cluster = &mut clusters[cluster_idx];
            if !cluster.qps.contains(&qp) {
                cluster.qps.push(qp);
            }
            if !cluster.rps.contains(&rp) {
                cluster.rps.push(rp);
            }
            q_to_cluster.insert(qp, cluster_idx);
            r_to_cluster.insert(rp, cluster_idx);
        }
    }

    // Solo records for unmatched parts.
    for qp in 0..n_q {
        if !q_to_cluster.contains_key(&qp) {
            clusters.push(Cluster {
                qps: vec![qp],
                rps: Vec::new(),
            });
        }
    }
    for rp in 0..n_r {
        if !r_to_cluster.contains_key(&rp) {
            clusters.push(Cluster {
                qps: Vec::new(),
                rps: vec![rp],
            });
        }
    }

    clusters
}

// --- Scoring -------------------------------------------------------

/// Convert one side's accumulated cost stream to a similarity in
/// `[0, 1]`.
///
/// Two design points worth knowing:
///
/// 1. The score has a **cliff**: if total cost exceeds the
///    length-dependent budget (`budget_log_base`,
///    `budget_short_floor`, `budget_tolerance` on
///    [`CompareConfig`]), the side scores zero. Below the cap,
///    similarity is `1 - total_cost / len_chars` — a clean linear
///    walk-down. The non-linearity is in the cliff, not in the
///    score curve, which keeps the math transparent.
/// 2. Tokens shorter than the floor get budget zero and any
///    non-zero cost fails the cap. That fail-closed behaviour is
///    deliberate: fuzzy-matching 1-2 char tokens (vessel hull
///    suffixes, isolated initials, 2-char Chinese given names) is
///    mostly noise and we'd rather miss those than over-fire.
fn costs_similarity(cfg: &CompareConfig, costs: &[f64]) -> f64 {
    if costs.is_empty() {
        return 0.0;
    }
    let effective_len = (costs.len() as f64 - cfg.budget_short_floor).max(1.0);
    let max_cost = effective_len.log(cfg.budget_log_base) * cfg.budget_tolerance;
    let total_cost: f64 = costs.iter().sum();
    if total_cost == 0.0 {
        return 1.0;
    }
    if total_cost > max_cost {
        return 0.0;
    }
    1.0 - (total_cost / costs.len() as f64)
}

/// Combine per-side similarities into one cluster score.
///
/// The product (rather than mean / min) is intentional: it's
/// punitive in the middle of the curve. A 99 %/50 % pair scores
/// 0.495, not 0.745 — either side being noisy zeros the cluster
/// quickly. That's the right shape for a recall-protective alert
/// threshold: above 0.8 means both sides are clean, below 0.5
/// means at least one side is unreliable, and the middle is a
/// triage zone for human review.
///
/// Solo clusters (one side empty) score 0.0 by construction —
/// they represent unmatched parts and have no pair-based
/// similarity to compute.
fn run_score(cfg: &CompareConfig, cluster: &Cluster, align: &AlignmentData) -> f64 {
    if cluster.qps.is_empty() || cluster.rps.is_empty() {
        return 0.0;
    }
    let mut q_costs: Vec<f64> = Vec::new();
    for &qp in &cluster.qps {
        let sub = &align.qry_costs[qp];
        if sub.is_empty() {
            q_costs.push(1.0);
        } else {
            q_costs.extend_from_slice(sub);
        }
    }
    let mut r_costs: Vec<f64> = Vec::new();
    for &rp in &cluster.rps {
        let sub = &align.res_costs[rp];
        if sub.is_empty() {
            r_costs.push(1.0);
        } else {
            r_costs.extend_from_slice(sub);
        }
    }
    costs_similarity(cfg, &q_costs) * costs_similarity(cfg, &r_costs)
}

// --- Public entry point --------------------------------------------

/// Score the alignment of two `NamePart` lists.
///
/// Callers should hand over the *residue* — parts that earlier stages
/// (symbol pairing, alias tagging, identifier matching) couldn't
/// explain by themselves — already canonicalised into positional
/// order (`tag_sort` for ORG/ENT, `align_person_name_order` for PER).
/// The function returns one [`Alignment`] per cluster, paired or
/// solo; every input part appears exactly once across the output.
/// Returned alignments carry `symbol = None` (residue distance is
/// non-symbolic by definition).
///
/// `config` overrides the cost / budget / clustering scalars. Pass
/// `None` (the default) to use the process-wide defaults — those
/// match industry-typical recall-protective tuning. Sweep scripts
/// build a fresh [`CompareConfig`] per iteration; matchers cache one
/// per request.
#[pyfunction]
#[pyo3(name = "compare_parts", signature = (qry, res, config = None))]
pub fn py_compare_parts(
    py: Python<'_>,
    qry: Vec<Py<NamePart>>,
    res: Vec<Py<NamePart>>,
    config: Option<&CompareConfig>,
) -> PyResult<Vec<Py<Alignment>>> {
    let cfg: &CompareConfig = config.unwrap_or(&DEFAULT_CONFIG);

    let n_q = qry.len();
    let n_r = res.len();

    // Pull comparable strings + char-lengths off the NameParts up front;
    // the alignment + clustering stages each iterate over them and
    // we'd otherwise pay the PyO3 borrow cost per cell.
    let mut q_comparable: Vec<String> = Vec::with_capacity(n_q);
    let mut q_lengths: Vec<usize> = Vec::with_capacity(n_q);
    for p in &qry {
        let part = p.bind(py).borrow();
        let c = part.comparable_str().to_string();
        q_lengths.push(c.chars().count());
        q_comparable.push(c);
    }
    let mut r_comparable: Vec<String> = Vec::with_capacity(n_r);
    let mut r_lengths: Vec<usize> = Vec::with_capacity(n_r);
    for p in &res {
        let part = p.bind(py).borrow();
        let c = part.comparable_str().to_string();
        r_lengths.push(c.chars().count());
        r_comparable.push(c);
    }

    let align = run_align(cfg, &q_comparable, &r_comparable);
    let clusters = run_cluster(cfg, &align, &q_lengths, &r_lengths, n_q, n_r);

    let mut out: Vec<Py<Alignment>> = Vec::with_capacity(clusters.len());
    for cluster in &clusters {
        let score = run_score(cfg, cluster, &align);
        let qps_parts: Vec<Py<NamePart>> =
            cluster.qps.iter().map(|&i| qry[i].clone_ref(py)).collect();
        let rps_parts: Vec<Py<NamePart>> =
            cluster.rps.iter().map(|&i| res[i].clone_ref(py)).collect();
        let alignment = Alignment::build(py, qps_parts, rps_parts, None, score, 1.0)?;
        out.push(Py::new(py, alignment)?);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn similar_pairs_loaded() {
        // Confusable-pair lookup must hit on both directions of a
        // listed pair without the caller normalising them — the
        // genscript pre-expands.
        assert!(SIMILAR_PAIRS.contains(&('0', 'o')));
        assert!(SIMILAR_PAIRS.contains(&('o', '0')));
        assert!(SIMILAR_PAIRS.contains(&('1', 'l')));
    }

    #[test]
    fn edit_cost_basic() {
        let cfg = CompareConfig::default();
        assert_eq!(edit_cost(&cfg, Op::Equal, Some('a'), Some('a')), 0.0);
        assert_eq!(edit_cost(&cfg, Op::Replace, Some('a'), Some('b')), 1.0);
        // Confusable
        assert_eq!(edit_cost(&cfg, Op::Replace, Some('0'), Some('o')), 0.7);
        // Digit
        assert_eq!(edit_cost(&cfg, Op::Replace, Some('5'), Some('8')), 1.5);
        // Lone SEP
        assert_eq!(edit_cost(&cfg, Op::Insert, None, Some(SEP)), 0.2);
        assert_eq!(edit_cost(&cfg, Op::Delete, Some(SEP), None), 0.2);
    }

    #[test]
    fn edit_cost_honours_config_overrides() {
        // Override the digit-mismatch cost — the same DP would
        // otherwise return the default 1.5.
        let cfg = CompareConfig {
            cost_digit: 0.3,
            ..CompareConfig::default()
        };
        assert_eq!(edit_cost(&cfg, Op::Replace, Some('5'), Some('8')), 0.3);
    }

    #[test]
    fn align_identical_strings() {
        let cfg = CompareConfig::default();
        let chars: Vec<char> = "putin".chars().collect();
        let steps = align_chars(&cfg, &chars, &chars);
        assert_eq!(steps.len(), 5);
        assert!(steps.iter().all(|s| s.op == Op::Equal));
    }

    #[test]
    fn align_one_substitute() {
        let cfg = CompareConfig::default();
        let q: Vec<char> = "putin".chars().collect();
        let r: Vec<char> = "potin".chars().collect();
        let steps = align_chars(&cfg, &q, &r);
        assert_eq!(steps.len(), 5);
        // 4 equal + 1 replace
        assert_eq!(steps.iter().filter(|s| s.op == Op::Equal).count(), 4);
        assert_eq!(steps.iter().filter(|s| s.op == Op::Replace).count(), 1);
    }

    #[test]
    fn costs_similarity_short_disables() {
        // The fail-closed property: 2-char tokens have budget zero,
        // so any non-zero edit fails the cap. Stops the matcher
        // from over-firing on 2-char Chinese given names, vessel
        // hull suffixes, initials, etc.
        let cfg = CompareConfig::default();
        let costs = vec![1.0, 0.0];
        assert_eq!(costs_similarity(&cfg, &costs), 0.0);
    }

    #[test]
    fn costs_similarity_zero_cost_gives_one() {
        let cfg = CompareConfig::default();
        let costs = vec![0.0, 0.0, 0.0, 0.0, 0.0];
        assert_eq!(costs_similarity(&cfg, &costs), 1.0);
    }

    #[test]
    fn align_transposition_prefers_distributive_path() {
        // Adjacent transpositions ("donlad" vs "donald") have two
        // equally-optimal alignments under unit cost — sub+sub
        // (concentrates 2.0 on one span, both sides) or
        // del+match+ins (1.0 to each side). The tie-break must
        // pick the distributive path, otherwise the per-side
        // budget cap rejects the cluster on a typo it should
        // accept.
        let cfg = CompareConfig::default();
        let q: Vec<char> = "donlad".chars().collect();
        let r: Vec<char> = "donald".chars().collect();
        let steps = align_chars(&cfg, &q, &r);
        let n_sub = steps.iter().filter(|s| s.op == Op::Replace).count();
        let n_del = steps.iter().filter(|s| s.op == Op::Delete).count();
        let n_ins = steps.iter().filter(|s| s.op == Op::Insert).count();
        // Distributive path: 1 delete + 1 insert + 0 substitutes.
        assert_eq!(n_sub, 0, "tie-break should avoid substitution");
        assert_eq!(n_del, 1);
        assert_eq!(n_ins, 1);
    }
}
