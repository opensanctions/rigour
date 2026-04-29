//! Residue-distance scoring for two `NamePart` lists.
//!
//! Reach for [`py_compare_parts`] when a name matcher has already
//! peeled off the parts it can explain by other means (symbol
//! pairing, alias tagging, identifier hits) and is left with a
//! residue that needs a fuzzy-match verdict — typically misspellings,
//! transliteration drift, or surface-form variants of the same
//! token.
//!
//! The function returns one [`Comparison`] per cluster of aligned
//! parts (paired or solo). Every input part appears in exactly one
//! `Comparison`, so a caller can sum / weight / threshold the result
//! without losing track of which inputs got accounted for.
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
use pyo3::types::PyTuple;
use serde::Deserialize;

use crate::names::part::NamePart;

/// Token boundary in the joined-name string the alignment runs over.
/// A single space works because `NamePart.comparable` is whitespace-
/// squashed casefold; if the contract ever drifts to admit literal
/// spaces inside a part's `comparable`, the SEP needs to move to a
/// non-character (e.g. `\u{0001}`) to stay unambiguous.
const SEP: char = ' ';

/// Multiplier on the per-side cost budget. Lower is stricter (less
/// edit tolerated before a cluster scores zero); higher is more
/// permissive. Callers tune this per scenario — KYC at onboarding
/// runs more permissive than payment screening.
const DEFAULT_FUZZY_TOLERANCE: f64 = 1.0;

// --- Edit-cost tiers ------------------------------------------------
//
// What an edit between `(qc, rc)` "costs" in the alignment. The
// downstream budget cap is per-side, so the *gap* between cheap
// (0.2) and expensive (1.5) edits is what determines whether a
// cluster squeaks under the cap or fails it. Tuning these values
// is one of the main levers in `plans/weighted-distance.md`'s
// "Systematizing and tuning" section.

/// Equal characters — no edit. Constant for symmetry; the function
/// doesn't actually call this.
const COST_EQUAL: f64 = 0.0;

/// Token boundary lost or gained on one side. Token merge/split
/// (`vanderbilt` ↔ `van der bilt`) is a common surface-form variant
/// of the same name; we charge it almost nothing so the alignment
/// doesn't refuse to bridge across whitespace artifacts.
const COST_SEP_DROP: f64 = 0.2;

/// Substitute between a confusable pair from
/// `resources/names/compare.yml` (`0`/`o`, `1`/`l`, …). OCR /
/// transliteration / homoglyph noise — the writer was probably
/// aiming at the same character.
const COST_CONFUSABLE: f64 = 0.7;

/// Default insert / delete / substitute cost. The unit; everything
/// else is calibrated relative to this.
const COST_DEFAULT: f64 = 1.0;

/// Edit involving a digit on either side (mismatched). Digits
/// identify specific things — vintage years, vessel hull numbers,
/// fund vintages — so a digit mismatch is evidence of a different
/// entity, not a typo.
const COST_DIGIT: f64 = 1.5;

// --- Per-side budget shape ------------------------------------------

/// Logarithm base in the per-side cost-budget formula
/// `log_BUDGET_LOG_BASE(max(len - BUDGET_SHORT_FLOOR, 1)) *
/// fuzzy_tolerance`. The base controls how aggressively the budget
/// grows with token length — smaller base = faster growth = more
/// permissive on long names. The current value is calibrated so a
/// 6-character token tolerates ~1.6 edits at default tolerance.
const BUDGET_LOG_BASE: f64 = 2.35;

/// Short-token floor: tokens shorter than this contribute zero to
/// the budget, so any non-zero edit fails the cap. This is the
/// fail-closed property — the matcher refuses to fuzzy-match on
/// 1-2 character tokens (vessel hull suffixes, isolated initials,
/// 2-char Chinese given names) where typo / distinct-entity signal
/// is too weak.
const BUDGET_SHORT_FLOOR: usize = 2;

// --- Clustering -----------------------------------------------------

/// Overlap fraction (matched chars / shorter-side length) above
/// which two parts pair into a cluster. A pair below this threshold
/// surfaces as solo records — the matched-character evidence is
/// too thin to claim the parts are talking about the same token.
/// The 0.51 value (i.e. "more than half") is the lowest value where
/// majority of the shorter token agrees; below half is dominated by
/// noise, above half is dominated by signal.
const CLUSTER_OVERLAP_MIN: f64 = 0.51;

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
/// (result side), keyed off the [edit-cost tiers](`COST_DEFAULT`)
/// at the top of the module.
///
/// Tier-selection is order-sensitive: SEP-drop checks come before
/// confusable lookup (so a SEP→non-SEP substitute falls through to
/// digit / default), and confusable beats digit (a `0`/`o` swap
/// gets COST_CONFUSABLE even though `0` is a digit).
fn edit_cost(op: Op, qc: Option<char>, rc: Option<char>) -> f64 {
    if op == Op::Equal {
        return COST_EQUAL;
    }
    if qc == Some(SEP) && rc.is_none() {
        return COST_SEP_DROP;
    }
    if rc == Some(SEP) && qc.is_none() {
        return COST_SEP_DROP;
    }
    if let (Some(q), Some(r)) = (qc, rc) {
        if SIMILAR_PAIRS.contains(&(q, r)) {
            return COST_CONFUSABLE;
        }
    }
    if matches!(qc, Some(c) if c.is_ascii_digit()) {
        return COST_DIGIT;
    }
    if matches!(rc, Some(c) if c.is_ascii_digit()) {
        return COST_DIGIT;
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
fn align_chars(q_chars: &[char], r_chars: &[char]) -> Vec<Step> {
    let n = q_chars.len();
    let m = r_chars.len();

    // Cost matrix; (n+1) x (m+1).
    let mut cost: Vec<Vec<f64>> = vec![vec![0.0; m + 1]; n + 1];
    let mut back: Vec<Vec<BackPtr>> = vec![vec![BackPtr::None; m + 1]; n + 1];

    for i in 1..=n {
        cost[i][0] = cost[i - 1][0] + edit_cost(Op::Delete, Some(q_chars[i - 1]), None);
        back[i][0] = BackPtr::Delete;
    }
    for j in 1..=m {
        cost[0][j] = cost[0][j - 1] + edit_cost(Op::Insert, None, Some(r_chars[j - 1]));
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
            let sub_cost = cost[i - 1][j - 1] + edit_cost(Op::Replace, Some(qc), Some(rc));
            // Delete from query
            let del_cost = cost[i - 1][j] + edit_cost(Op::Delete, Some(qc), None);
            // Insert from result
            let ins_cost = cost[i][j - 1] + edit_cost(Op::Insert, None, Some(rc));

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
fn run_align(qry_comparable: &[String], res_comparable: &[String]) -> AlignmentData {
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

    let steps = align_chars(&q_chars, &r_chars);

    // Walk the alignment, advancing part-cursors on each SEP.
    let mut qry_idx: usize = 0;
    let mut res_idx: usize = 0;

    for step in &steps {
        let qc = step.qc;
        let rc = step.rc;
        if step.op == Op::Equal {
            if qc.is_some() && qc != Some(SEP) && rc.is_some() && rc != Some(SEP) {
                *overlaps.entry((qry_idx, res_idx)).or_insert(0) += 1;
            }
        }
        let cost = edit_cost(step.op, qc, rc);
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

/// Pair query/result parts into clusters, with transitive closure.
///
/// A pair `(qp, rp)` joins a cluster when the alignment matched more
/// than half the shorter part's characters between them — strong
/// enough overlap that they're plausibly the same token, ignoring
/// noise. Transitive closure folds in chained pairings, so the
/// `vanderbilt` ↔ `[van, der, bilt]` token-split case lands as one
/// cluster instead of three near-misses.
///
/// Parts that no overlap pair clears the threshold for surface as
/// solo clusters at the end. Every input part appears in exactly
/// one output cluster — paired or solo.
fn run_cluster(
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
        if frac > CLUSTER_OVERLAP_MIN {
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
///    length-dependent budget (see [`BUDGET_LOG_BASE`] and
///    [`BUDGET_SHORT_FLOOR`]), the side scores zero. Below the cap,
///    similarity is `1 - total_cost / len_chars` — a clean linear
///    walk-down. The non-linearity is in the cliff, not in the
///    score curve, which keeps the math transparent.
/// 2. Tokens shorter than the floor get budget zero and any
///    non-zero cost fails the cap. That fail-closed behaviour is
///    deliberate: fuzzy-matching 1-2 char tokens (vessel hull
///    suffixes, isolated initials, 2-char Chinese given names) is
///    mostly noise and we'd rather miss those than over-fire.
fn costs_similarity(costs: &[f64], fuzzy_tolerance: f64) -> f64 {
    if costs.is_empty() {
        return 0.0;
    }
    let effective_len = (costs.len() as i64 - BUDGET_SHORT_FLOOR as i64).max(1) as f64;
    let max_cost = effective_len.log(BUDGET_LOG_BASE) * fuzzy_tolerance;
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
fn run_score(cluster: &Cluster, align: &AlignmentData, fuzzy_tolerance: f64) -> f64 {
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
    costs_similarity(&q_costs, fuzzy_tolerance) * costs_similarity(&r_costs, fuzzy_tolerance)
}

// --- Comparison pyclass --------------------------------------------

/// One cluster from the [`py_compare_parts`] return — either a
/// paired record where parts on both sides aligned, or a solo
/// record where a part went unaccounted-for.
///
/// Every input `NamePart` appears in exactly one `Comparison`,
/// which is what lets a caller iterate the result and compute a
/// total — the paired clusters carry positive evidence, the solo
/// clusters carry the "unexplained part" penalty.
///
/// `qps` and `rps` reference the same `NamePart` Python objects
/// the caller passed in, so identity is preserved across the
/// boundary.
#[pyclass(module = "rigour._core")]
pub struct Comparison {
    #[pyo3(get)]
    pub qps: Py<PyTuple>,
    #[pyo3(get)]
    pub rps: Py<PyTuple>,
    /// Similarity in `[0, 1]`. `0.0` for solo clusters; otherwise the
    /// product of per-side similarities (see `run_score` for shape).
    #[pyo3(get)]
    pub score: f64,
}

#[pymethods]
impl Comparison {
    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let qps_repr: String = self.qps.bind(py).repr()?.extract()?;
        let rps_repr: String = self.rps.bind(py).repr()?.extract()?;
        Ok(format!(
            "<Comparison(qps={}, rps={}, score={:.4})>",
            qps_repr, rps_repr, self.score
        ))
    }
}

// --- Public entry point --------------------------------------------

/// Score the alignment of two `NamePart` lists.
///
/// Callers should hand over the *residue* — parts that earlier stages
/// (symbol pairing, alias tagging, identifier matching) couldn't
/// explain by themselves — already canonicalised into positional
/// order (`tag_sort` for ORG/ENT, `align_person_name_order` for PER).
/// The function returns one [`Comparison`] per cluster, paired or
/// solo; every input part appears exactly once across the output.
///
/// `fuzzy_tolerance` rescales the per-side cost budget. Higher = more permissive
/// (KYC-onboarding profile); lower = stricter (payment-screening
/// profile). The default of `1.0` matches industry-typical recall-
/// protective tuning.
#[pyfunction]
#[pyo3(name = "compare_parts", signature = (qry, res, fuzzy_tolerance = DEFAULT_FUZZY_TOLERANCE))]
pub fn py_compare_parts(
    py: Python<'_>,
    qry: Vec<Py<NamePart>>,
    res: Vec<Py<NamePart>>,
    fuzzy_tolerance: f64,
) -> PyResult<Vec<Py<Comparison>>> {
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

    let align = run_align(&q_comparable, &r_comparable);
    let clusters = run_cluster(&align, &q_lengths, &r_lengths, n_q, n_r);

    let mut out: Vec<Py<Comparison>> = Vec::with_capacity(clusters.len());
    for cluster in &clusters {
        let score = run_score(cluster, &align, fuzzy_tolerance);
        let qps_parts: Vec<Py<NamePart>> =
            cluster.qps.iter().map(|&i| qry[i].clone_ref(py)).collect();
        let rps_parts: Vec<Py<NamePart>> =
            cluster.rps.iter().map(|&i| res[i].clone_ref(py)).collect();
        let qps_tuple = PyTuple::new(py, &qps_parts)?.unbind();
        let rps_tuple = PyTuple::new(py, &rps_parts)?.unbind();
        let comp = Comparison {
            qps: qps_tuple,
            rps: rps_tuple,
            score,
        };
        out.push(Py::new(py, comp)?);
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
        assert_eq!(edit_cost(Op::Equal, Some('a'), Some('a')), 0.0);
        assert_eq!(edit_cost(Op::Replace, Some('a'), Some('b')), 1.0);
        // Confusable
        assert_eq!(edit_cost(Op::Replace, Some('0'), Some('o')), 0.7);
        // Digit
        assert_eq!(edit_cost(Op::Replace, Some('5'), Some('8')), 1.5);
        // Lone SEP
        assert_eq!(edit_cost(Op::Insert, None, Some(SEP)), 0.2);
        assert_eq!(edit_cost(Op::Delete, Some(SEP), None), 0.2);
    }

    #[test]
    fn align_identical_strings() {
        let chars: Vec<char> = "putin".chars().collect();
        let steps = align_chars(&chars, &chars);
        assert_eq!(steps.len(), 5);
        assert!(steps.iter().all(|s| s.op == Op::Equal));
    }

    #[test]
    fn align_one_substitute() {
        let q: Vec<char> = "putin".chars().collect();
        let r: Vec<char> = "potin".chars().collect();
        let steps = align_chars(&q, &r);
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
        let costs = vec![1.0, 0.0];
        assert_eq!(costs_similarity(&costs, 1.0), 0.0);
    }

    #[test]
    fn costs_similarity_zero_cost_gives_one() {
        let costs = vec![0.0, 0.0, 0.0, 0.0, 0.0];
        assert_eq!(costs_similarity(&costs, 1.0), 1.0);
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
        let q: Vec<char> = "donlad".chars().collect();
        let r: Vec<char> = "donald".chars().collect();
        let steps = align_chars(&q, &r);
        let n_sub = steps.iter().filter(|s| s.op == Op::Replace).count();
        let n_del = steps.iter().filter(|s| s.op == Op::Delete).count();
        let n_ins = steps.iter().filter(|s| s.op == Op::Insert).count();
        // Distributive path: 1 delete + 1 insert + 0 substitutes.
        assert_eq!(n_sub, 0, "tie-break should avoid substitution");
        assert_eq!(n_del, 1);
        assert_eq!(n_ins, 1);
    }
}
