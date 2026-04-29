//! Residue-distance comparator — Rust port of the Python prototype
//! `compare_parts_orig` (in `contrib/name_comparison/comparators/`).
//!
//! Three internal stages, mirroring the prototype:
//!
//! 1. `align` — cost-folded Wagner-Fischer with traceback over the
//!    SEP-joined NamePart strings. Walks the alignment to accumulate
//!    per-part cost streams + per-pair overlap counts.
//! 2. `cluster` — pair `(qry_part, res_part)` into clusters via the
//!    0.51 overlap rule with transitive closure (matches the prototype's
//!    behaviour exactly so phase-3 parity is achievable).
//! 3. `score` — product of per-side similarities, gated by a
//!    log-budget cap (also mirrors the prototype).
//!
//! Returns `Vec<Comparison>` where each `Comparison` is a paired or
//! solo cluster. Every input NamePart appears in exactly one
//! Comparison.
//!
//! Spec context: `plans/weighted-distance.md`. This file deliberately
//! does NOT optimise — the goal of the first port is parity (within
//! float tolerance) with the Python prototype, measured via
//! `qsv diff` between `compare_python` and `compare_rust` per-case
//! dumps in the harness.

use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use pyo3::prelude::*;
use pyo3::types::PyTuple;
use serde::Deserialize;

use crate::names::part::NamePart;

/// SEP character used to join NamePart `comparable` strings before
/// running the alignment. A single space is fine because `comparable`
/// forms are casefolded with whitespace squashed (analyze_names
/// guarantees this); if the contract ever drifts, change to a
/// non-character like `\u{0001}`.
const SEP: char = ' ';

/// Bias on the per-side length budget. Mirrors logic_v2's
/// `nm_fuzzy_cutoff_factor` default. Hard-coded for now; the harness
/// can plumb a real config later if iteration justifies.
const DEFAULT_BIAS: f64 = 1.0;

// --- Cost table loaded from compiled YAML ------------------------------

#[derive(Debug, Deserialize)]
struct CompareData {
    similar_pairs: Vec<[String; 2]>,
}

const COMPARE_JSON: &str = include_str!("../../data/names/compare.json");

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

/// Char-pair cost lookup. Mirrors `compare_parts_orig._edit_cost`.
fn edit_cost(op: Op, qc: Option<char>, rc: Option<char>) -> f64 {
    if op == Op::Equal {
        return 0.0;
    }
    if qc == Some(SEP) && rc.is_none() {
        return 0.2;
    }
    if rc == Some(SEP) && qc.is_none() {
        return 0.2;
    }
    if let (Some(q), Some(r)) = (qc, rc) {
        if SIMILAR_PAIRS.contains(&(q, r)) {
            return 0.7;
        }
    }
    if matches!(qc, Some(c) if c.is_ascii_digit()) {
        return 1.5;
    }
    if matches!(rc, Some(c) if c.is_ascii_digit()) {
        return 1.5;
    }
    1.0
}

// --- Wagner-Fischer DP with traceback ----------------------------------

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
    Match,    // diagonal, equal
    Substitute,
    Insert,   // came from left (rc consumed, qc not)
    Delete,   // came from above (qc consumed, rc not)
}

/// One alignment step. `qc` / `rc` track which character on each
/// side this step consumed (or `None` if the step is one-sided).
#[derive(Clone, Debug)]
struct Step {
    op: Op,
    qc: Option<char>,
    rc: Option<char>,
}

/// Run cost-folded Wagner-Fischer over (q_chars, r_chars) and return
/// the alignment as a forward sequence of edit steps.
///
/// The cost-folded approach uses `edit_cost` directly inside the DP,
/// so the optimal alignment is genuinely optimal under the cost
/// model — distinct from the prototype's unit-cost-then-rescore via
/// `Levenshtein.opcodes`. This is the spec's chosen design (see plan
/// § Cost-folded DP); a small amount of scoring drift vs. the Python
/// prototype on tied-alignment cases is expected.
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

            // Pick minimum. Tie-breaking: match wins outright on cost
            // tie (always preferred for `equal` runs); on cost-tied
            // non-match paths we prefer one-sided edits (delete /
            // insert) over substitution.
            //
            // Why: substitution attributes cost to **both** sides
            // (qry_costs gets the cost for the consumed qc AND
            // res_costs gets it for the consumed rc), while delete
            // attributes only to qry and insert only to res. For
            // transposition-like patterns ("Donlad" vs "Donald"),
            // sub+sub doubles cost on a single span; del+match+ins
            // splits cost across sides. Total work is identical, but
            // the per-side budget cap in `_costs_similarity` cares
            // about distribution, not just totals — del+ins survives
            // the cap where sub+sub fails it. Picking the more
            // distributive alignment respects that downstream
            // accounting.
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

// --- Alignment walk: per-part cost streams + per-pair overlaps --------

struct AlignmentData {
    /// `qry_costs[i]` — char-level costs accumulated against query
    /// part `i` (in the order the alignment walked through them).
    qry_costs: Vec<Vec<f64>>,
    /// Same for result side.
    res_costs: Vec<Vec<f64>>,
    /// `(q_idx, r_idx) -> equal-character count`. Only `Equal` steps
    /// where neither side is SEP contribute; populated as the walk
    /// advances the part-cursors.
    overlaps: HashMap<(usize, usize), u32>,
}

fn run_align(
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

    let steps = align_chars(&q_chars, &r_chars);

    // Walk the alignment, advancing part-cursors on each SEP.
    let mut qry_idx: usize = 0;
    let mut res_idx: usize = 0;

    for step in &steps {
        let qc = step.qc;
        let rc = step.rc;
        if step.op == Op::Equal {
            if qc.is_some()
                && qc != Some(SEP)
                && rc.is_some()
                && rc != Some(SEP)
            {
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

// --- Clustering --------------------------------------------------------

/// One alignment cluster — qry-side + res-side part indices.
struct Cluster {
    qps: Vec<usize>,
    rps: Vec<usize>,
}

/// Group `(q_idx, r_idx)` overlap pairs into clusters via the 0.51
/// overlap rule with transitive closure. Mirrors
/// `compare_parts_orig._cluster`.
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

    // Iterate overlap pairs in stable order — sort by (q_idx, r_idx)
    // to mirror Python dict insertion-order behaviour for cases where
    // alignment populates them in that sequence.
    let mut entries: Vec<((usize, usize), u32)> = align
        .overlaps
        .iter()
        .map(|(&k, &v)| (k, v))
        .collect();
    entries.sort_by_key(|(k, _)| *k);

    for ((qp, rp), overlap) in entries {
        let q_len = qry_lengths[qp];
        let r_len = res_lengths[rp];
        let min_len = q_len.min(r_len);
        if min_len == 0 {
            continue;
        }
        let frac = overlap as f64 / min_len as f64;
        if frac > 0.51 {
            // Find existing cluster for either side, else create one.
            let cluster_idx = match (q_to_cluster.get(&qp), r_to_cluster.get(&rp)) {
                (Some(&i), _) => i,
                (None, Some(&i)) => i,
                (None, None) => {
                    clusters.push(Cluster { qps: Vec::new(), rps: Vec::new() });
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

// --- Scoring -----------------------------------------------------------

/// Per-side similarity from accumulated char-level costs.
/// Mirrors `compare_parts_orig._costs_similarity`.
fn costs_similarity(costs: &[f64], bias: f64) -> f64 {
    if costs.is_empty() {
        return 0.0;
    }
    let len_minus_2 = (costs.len() as i64 - 2).max(1) as f64;
    let max_cost = len_minus_2.log(2.35) * bias;
    let total_cost: f64 = costs.iter().sum();
    if total_cost == 0.0 {
        return 1.0;
    }
    if total_cost > max_cost {
        return 0.0;
    }
    1.0 - (total_cost / costs.len() as f64)
}

/// Per-cluster score: product of per-side similarities. Solo clusters
/// score 0.0 by definition.
fn run_score(cluster: &Cluster, align: &AlignmentData, bias: f64) -> f64 {
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
    costs_similarity(&q_costs, bias) * costs_similarity(&r_costs, bias)
}

// --- Comparison pyclass ------------------------------------------------

/// One residue-distance cluster.
///
/// Either a paired record (both sides non-empty) representing parts
/// that align with each other, or a solo record (one side empty)
/// representing an unmatched part. Every input NamePart appears in
/// exactly one Comparison.
///
/// Returned as a flat `Vec<Comparison>` from
/// [`py_compare_parts`]; nomenklatura wraps each into a `Match` with
/// matcher-policy weights applied.
#[pyclass(module = "rigour._core")]
pub struct Comparison {
    /// Query-side parts in this cluster (`Py<NamePart>` references
    /// preserve identity with the inputs).
    #[pyo3(get)]
    pub qps: Py<PyTuple>,
    /// Result-side parts.
    #[pyo3(get)]
    pub rps: Py<PyTuple>,
    /// Score in `[0, 1]`. Solo records (one side empty) score 0.0.
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

// --- Public entry point ------------------------------------------------

/// Score the alignment of two NamePart lists.
///
/// Inputs are residue parts (post-pruning, post-symbol-pairing,
/// already tag-sorted by the caller). Output is one `Comparison`
/// per cluster, including solo records for unmatched parts.
#[pyfunction]
#[pyo3(name = "compare_parts", signature = (qry, res, bias = DEFAULT_BIAS))]
pub fn py_compare_parts(
    py: Python<'_>,
    qry: Vec<Py<NamePart>>,
    res: Vec<Py<NamePart>>,
    bias: f64,
) -> PyResult<Vec<Py<Comparison>>> {
    let n_q = qry.len();
    let n_r = res.len();

    // Pre-extract the comparable strings + lengths so the alignment +
    // clustering passes don't re-bind on every read.
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
        let score = run_score(cluster, &align, bias);
        let qps_parts: Vec<Py<NamePart>> = cluster
            .qps
            .iter()
            .map(|&i| qry[i].clone_ref(py))
            .collect();
        let rps_parts: Vec<Py<NamePart>> = cluster
            .rps
            .iter()
            .map(|&i| res[i].clone_ref(py))
            .collect();
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
        // Sanity: the JSON deserialises and at least one known pair
        // is present (bidirectional, since the genscript expanded).
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
        // 2-char token with nonzero cost: log(max(0,1)) = 0, total > max
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
        // "donlad" vs "donald" has two equally-optimal alignments at
        // total cost 2.0: sub+sub or del+match+ins. The tie-break
        // prefers del+ins so cost distributes 1.0 per side instead of
        // doubling on a single cell. This is what lets the per-side
        // budget cap accept the match.
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
