//! Symbol pairing — align the symbol spans of two [`Name`]s into
//! coverage-maximal pairings.
//!
//! The cheap short-cut for the matcher: given two names where the
//! tagger has already attached semantic annotations (NAME symbols
//! for recognised persons, ORG_CLASS for legal forms, and so on),
//! produce alignments between symbol spans that score
//! identically to whatever the downstream string-distance layer
//! would have computed on the same tokens.
//!
//! Full design: `plans/rust-pairings.md`. Four phases, all in
//! Rust: (1) intra-symbol greedy binding to `min(N, M)` edges,
//! (2) same-category subsumption prune, (3) DFS enumeration of
//! maximal coverings with a `(qmask, rmask, categories)` dedup
//! key, (4) emit.

use std::collections::{HashMap, HashSet};

use pyo3::prelude::*;
use pyo3::types::{PyList, PyTuple};

use crate::names::name::Name;
use crate::names::part::{NamePart, Span};
use crate::names::symbol::{Symbol, SymbolCategory};
use crate::names::tag::NamePartTag;

/// Maximum name-part count the `u64` bitmask fast path supports.
/// Names larger than this short-circuit to the empty fallback
/// rather than falling back to a `Vec<u64>` slow path — names
/// that large are almost always data errors.
const MAX_PARTS: usize = 64;

/// Per-part info retained at span-collection time. The `tag` field
/// is needed for `NAME` / `NICK` `can_match` filtering; `char_len`
/// is needed for the `INITIAL` single-character rule.
#[derive(Clone, Debug)]
struct PartInfo {
    index: u32,
    tag: NamePartTag,
    char_len: usize,
}

/// One span on one side of the pairing, flattened for Rust-side
/// use. `parts` preserves the span's original (position) order so
/// `parts[0]` means the same thing here as in the pre-port
/// Python's `span.parts[0]`.
#[derive(Clone, Debug)]
struct SpanInfo {
    parts: Vec<PartInfo>,
    mask: u64,
    symbol: Symbol,
}

/// A candidate edge — an intra-symbol binding of one qspan to one
/// rspan. Internal to the algorithm; the exposed type is
/// [`PairedEdge`].
#[derive(Clone, Debug)]
struct Edge {
    qmask: u64,
    rmask: u64,
    qparts: Vec<u32>,
    rparts: Vec<u32>,
    symbol: Symbol,
}

/// One paired edge in a returned pairing. Crosses the PyO3
/// boundary as a frozen `#[pyclass]`; the Python wrapper
/// (`rigour.names.symbol.pair_symbols`) converts each `PairedEdge`
/// to a `SymbolEdge` dataclass, resolving `query_parts` /
/// `result_parts` indices against the source `Name.parts`.
#[pyclass(module = "rigour._core", frozen)]
pub struct PairedEdge {
    /// Indices into `query.parts` covered by this edge, ascending.
    #[pyo3(get)]
    pub query_parts: Py<PyTuple>,
    /// Indices into `result.parts` covered by this edge, ascending.
    #[pyo3(get)]
    pub result_parts: Py<PyTuple>,
    /// The shared `Symbol` both sides carry.
    #[pyo3(get)]
    pub symbol: Py<Symbol>,
}

/// Read the spans off a [`Name`], flattening each one into a
/// [`SpanInfo`] with its part indices, tags, character lengths,
/// and the carried `Symbol`. Sorted by `(min_part_idx, max_part_idx)`
/// — the greedy-binding pass relies on deterministic order.
fn collect_spans(py: Python<'_>, name: &Name) -> PyResult<Vec<SpanInfo>> {
    let spans_list = name.spans.bind(py);
    let mut out: Vec<SpanInfo> = Vec::with_capacity(spans_list.len());
    for item in spans_list.iter() {
        let span = item.cast::<Span>()?.borrow();
        let parts_tuple = span.parts.bind(py);
        let mut parts: Vec<PartInfo> = Vec::with_capacity(parts_tuple.len());
        let mut mask: u64 = 0;
        for part_item in parts_tuple.iter() {
            let part = part_item.cast::<NamePart>()?.borrow();
            let info = PartInfo {
                index: part.index,
                tag: part.tag,
                char_len: part.form.bind(py).to_str()?.chars().count(),
            };
            if info.index < MAX_PARTS as u32 {
                mask |= 1u64 << info.index;
            }
            parts.push(info);
        }
        let symbol: Symbol = span.symbol.bind(py).extract()?;
        out.push(SpanInfo {
            parts,
            mask,
            symbol,
        });
    }
    out.sort_by_key(|s| {
        let min_idx = s.parts.iter().map(|p| p.index).min().unwrap_or(u32::MAX);
        let max_idx = s.parts.iter().map(|p| p.index).max().unwrap_or(u32::MAX);
        (min_idx, max_idx)
    });
    Ok(out)
}

/// Per-edge compatibility filter, mirroring `Pairing.can_pair`
/// with the one deliberate deviation: `NAME` / `NICK` checks use
/// the full cartesian product instead of `zip()`-truncation.
fn spans_can_pair(qspan: &SpanInfo, rspan: &SpanInfo) -> bool {
    match qspan.symbol.category {
        SymbolCategory::INITIAL => {
            // At least one side must have a single-character first
            // part — the INITIAL symbol semantic ("J stands in for
            // John"). Both multi-char would mean the symbol was
            // mis-applied.
            let q_first_len = qspan.parts.first().map(|p| p.char_len).unwrap_or(0);
            let r_first_len = rspan.parts.first().map(|p| p.char_len).unwrap_or(0);
            !(q_first_len > 1 && r_first_len > 1)
        }
        SymbolCategory::NAME | SymbolCategory::NICK => {
            for qp in &qspan.parts {
                for rp in &rspan.parts {
                    if !qp.tag.can_match(rp.tag) {
                        return false;
                    }
                }
            }
            true
        }
        _ => true,
    }
}

/// Step 1 — build the candidate-edge set.
///
/// Group qspans and rspans by `Symbol` (full identity, not just
/// category); for each shared symbol, greedy-bind qspan to the
/// first unbound rspan that passes [`spans_can_pair`]. Produces
/// at most `min(|qspans|, |rspans|)` edges per symbol.
fn build_candidate_edges(q_spans: &[SpanInfo], r_spans: &[SpanInfo]) -> Vec<Edge> {
    let mut q_by_sym: HashMap<Symbol, Vec<usize>> = HashMap::new();
    for (i, s) in q_spans.iter().enumerate() {
        q_by_sym.entry(s.symbol.clone()).or_default().push(i);
    }
    let mut r_by_sym: HashMap<Symbol, Vec<usize>> = HashMap::new();
    for (i, s) in r_spans.iter().enumerate() {
        r_by_sym.entry(s.symbol.clone()).or_default().push(i);
    }

    let mut edges: Vec<Edge> = Vec::new();
    for (sym, q_indices) in &q_by_sym {
        let Some(r_indices) = r_by_sym.get(sym) else {
            continue;
        };
        let mut r_taken: Vec<bool> = vec![false; r_indices.len()];
        for &qi in q_indices {
            let qspan = &q_spans[qi];
            for (r_pos, &ri) in r_indices.iter().enumerate() {
                if r_taken[r_pos] {
                    continue;
                }
                let rspan = &r_spans[ri];
                if spans_can_pair(qspan, rspan) {
                    r_taken[r_pos] = true;
                    let mut qparts: Vec<u32> = qspan.parts.iter().map(|p| p.index).collect();
                    let mut rparts: Vec<u32> = rspan.parts.iter().map(|p| p.index).collect();
                    qparts.sort_unstable();
                    rparts.sort_unstable();
                    edges.push(Edge {
                        qmask: qspan.mask,
                        rmask: rspan.mask,
                        qparts,
                        rparts,
                        symbol: sym.clone(),
                    });
                    break;
                }
            }
        }
    }
    edges
}

/// Step 2 — drop same-category edges strictly dominated by
/// another edge on both the query and result masks.
fn prune_subsumed(edges: &mut Vec<Edge>) {
    let n = edges.len();
    if n < 2 {
        return;
    }
    let mut keep: Vec<bool> = vec![true; n];
    for i in 0..n {
        for j in 0..n {
            if i == j || !keep[j] {
                continue;
            }
            let ei = &edges[i];
            let ej = &edges[j];
            if ei.symbol.category != ej.symbol.category {
                continue;
            }
            let q_subset = (ej.qmask | ei.qmask) == ei.qmask;
            let r_subset = (ej.rmask | ei.rmask) == ei.rmask;
            let q_strict = ej.qmask != ei.qmask;
            let r_strict = ej.rmask != ei.rmask;
            if q_subset && r_subset && q_strict && r_strict {
                keep[j] = false;
            }
        }
    }
    let mut idx = 0;
    edges.retain(|_| {
        let k = keep[idx];
        idx += 1;
        k
    });
}

/// Canonical sort key for edges going into the DFS. Puts
/// earlier-in-name edges first, then stabilises on category and
/// symbol id so ties break deterministically.
fn edge_sort_key(e: &Edge) -> (u32, u32, u8, String) {
    let qmin = e.qparts.first().copied().unwrap_or(u32::MAX);
    let rmin = e.rparts.first().copied().unwrap_or(u32::MAX);
    (qmin, rmin, e.symbol.category as u8, e.symbol.id.to_string())
}

/// Step 3 — enumerate maximal non-conflicting edge selections,
/// deduplicated on `(qmask, rmask, sorted categories)`.
///
/// The first element of the returned list is always the empty
/// selection (index list `[]`). If edges exist and at least one
/// maximal non-empty covering is found, it's appended; if none
/// are found (all edges conflict trivially, unlikely but
/// defensively covered) the empty selection is the only output.
fn enumerate_coverings(edges: &[Edge]) -> Vec<Vec<usize>> {
    let mut results: Vec<Vec<usize>> = vec![vec![]];
    let mut seen: HashSet<(u64, u64, Vec<u8>)> = HashSet::new();
    seen.insert((0, 0, Vec::new()));

    let mut picked: Vec<usize> = Vec::new();
    dfs(edges, 0, 0, 0, &mut picked, &mut results, &mut seen);
    results
}

fn dfs(
    edges: &[Edge],
    i: usize,
    qmask: u64,
    rmask: u64,
    picked: &mut Vec<usize>,
    results: &mut Vec<Vec<usize>>,
    seen: &mut HashSet<(u64, u64, Vec<u8>)>,
) {
    if i == edges.len() {
        // Maximality check — every un-picked edge must conflict
        // with the current coverage, otherwise we skipped an
        // extension and the selection isn't maximal.
        for (j, edge) in edges.iter().enumerate() {
            if picked.contains(&j) {
                continue;
            }
            if (edge.qmask & qmask) == 0 && (edge.rmask & rmask) == 0 {
                return;
            }
        }
        let mut cats: Vec<u8> = picked
            .iter()
            .map(|&j| edges[j].symbol.category as u8)
            .collect();
        cats.sort_unstable();
        let key = (qmask, rmask, cats);
        if seen.insert(key) {
            results.push(picked.clone());
        }
        return;
    }
    // Skip edge i.
    dfs(edges, i + 1, qmask, rmask, picked, results, seen);
    // Take edge i if compatible.
    let e = &edges[i];
    if (e.qmask & qmask) == 0 && (e.rmask & rmask) == 0 {
        picked.push(i);
        dfs(
            edges,
            i + 1,
            qmask | e.qmask,
            rmask | e.rmask,
            picked,
            results,
            seen,
        );
        picked.pop();
    }
}

/// Build the empty-only output (`[()]`) — returned when either
/// name exceeds `MAX_PARTS`, when no spans exist on either side,
/// or when no candidate edges survive.
fn empty_output(py: Python<'_>) -> PyResult<Py<PyList>> {
    let empty_tuple = PyTuple::empty(py);
    let list = PyList::new(py, [empty_tuple])?;
    Ok(list.unbind())
}

/// Convert a coverage selection into a Python tuple of
/// [`PairedEdge`] instances.
fn build_pairing(
    py: Python<'_>,
    edges: &[Edge],
    indices: &[usize],
    q_symbols: &HashMap<Symbol, Py<Symbol>>,
) -> PyResult<Py<PyTuple>> {
    let mut edge_objs: Vec<Py<PairedEdge>> = Vec::with_capacity(indices.len());
    for &i in indices {
        let e = &edges[i];
        let qparts_tuple = PyTuple::new(py, &e.qparts)?.unbind();
        let rparts_tuple = PyTuple::new(py, &e.rparts)?.unbind();
        // Re-use a single Py<Symbol> per distinct Symbol so two
        // edges carrying the same symbol compare as Python
        // `is`-equal at the boundary.
        let symbol_py = q_symbols
            .get(&e.symbol)
            .map(|s| s.clone_ref(py))
            .unwrap_or_else(|| Py::new(py, e.symbol.clone()).expect("Py::new<Symbol> cannot fail"));
        let edge = PairedEdge {
            query_parts: qparts_tuple,
            result_parts: rparts_tuple,
            symbol: symbol_py,
        };
        edge_objs.push(Py::new(py, edge)?);
    }
    Ok(PyTuple::new(py, &edge_objs)?.unbind())
}

/// Collect the query-side `Py<Symbol>` objects into a map keyed on
/// the Rust-owned `Symbol`, so `build_pairing` can reuse the
/// tagger-emitted Python objects instead of minting fresh ones per
/// edge. Cheap either way (Symbols are `Arc<str>`-interned) but
/// this preserves identity for callers that care.
fn collect_symbol_py(py: Python<'_>, name: &Name) -> PyResult<HashMap<Symbol, Py<Symbol>>> {
    let spans_list = name.spans.bind(py);
    let mut out: HashMap<Symbol, Py<Symbol>> = HashMap::new();
    for item in spans_list.iter() {
        let span = item.cast::<Span>()?.borrow();
        let sym_py = span.symbol.clone_ref(py);
        let sym: Symbol = span.symbol.bind(py).extract()?;
        out.entry(sym).or_insert(sym_py);
    }
    Ok(out)
}

/// PyO3 entry point — see the Python-side docstring on
/// `rigour.names.symbol.pair_symbols` for the semantic spec.
#[pyfunction]
#[pyo3(name = "pair_symbols")]
pub fn py_pair_symbols(
    py: Python<'_>,
    query: PyRef<'_, Name>,
    result: PyRef<'_, Name>,
) -> PyResult<Py<PyList>> {
    let q_parts_len = query.parts.bind(py).len();
    let r_parts_len = result.parts.bind(py).len();
    if q_parts_len > MAX_PARTS || r_parts_len > MAX_PARTS {
        return empty_output(py);
    }

    let q_spans = collect_spans(py, &query)?;
    let r_spans = collect_spans(py, &result)?;
    if q_spans.is_empty() || r_spans.is_empty() {
        return empty_output(py);
    }

    let mut edges = build_candidate_edges(&q_spans, &r_spans);
    prune_subsumed(&mut edges);
    edges.sort_by_cached_key(edge_sort_key);

    let coverings = enumerate_coverings(&edges);

    let q_symbols = collect_symbol_py(py, &query)?;

    let pairings: Vec<Py<PyTuple>> = coverings
        .iter()
        .map(|indices| build_pairing(py, &edges, indices, &q_symbols))
        .collect::<PyResult<Vec<_>>>()?;

    Ok(PyList::new(py, &pairings)?.unbind())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn mk_part(index: u32, tag: NamePartTag, char_len: usize) -> PartInfo {
        PartInfo {
            index,
            tag,
            char_len,
        }
    }

    fn mk_span(parts: Vec<PartInfo>, symbol: Symbol) -> SpanInfo {
        let mut mask: u64 = 0;
        for p in &parts {
            mask |= 1u64 << p.index;
        }
        SpanInfo {
            parts,
            mask,
            symbol,
        }
    }

    fn sym(cat: SymbolCategory, id: &str) -> Symbol {
        Symbol::from_str(cat, id)
    }

    #[test]
    fn no_shared_symbols_yields_no_edges() {
        let q = vec![mk_span(
            vec![mk_part(0, NamePartTag::UNSET, 4)],
            sym(SymbolCategory::NAME, "QA"),
        )];
        let r = vec![mk_span(
            vec![mk_part(0, NamePartTag::UNSET, 4)],
            sym(SymbolCategory::NAME, "QB"),
        )];
        let edges = build_candidate_edges(&q, &r);
        assert!(edges.is_empty());
    }

    #[test]
    fn single_symbol_one_edge() {
        let q = vec![mk_span(
            vec![mk_part(0, NamePartTag::UNSET, 4)],
            sym(SymbolCategory::NAME, "QJohn"),
        )];
        let r = vec![mk_span(
            vec![mk_part(0, NamePartTag::UNSET, 4)],
            sym(SymbolCategory::NAME, "QJohn"),
        )];
        let edges = build_candidate_edges(&q, &r);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].qparts, vec![0]);
        assert_eq!(edges[0].rparts, vec![0]);
    }

    #[test]
    fn intra_symbol_greedy_min_n_m() {
        // 2 qspans, 1 rspan for the same symbol → 1 edge, first
        // qspan bound.
        let qsym = sym(SymbolCategory::NAME, "QFoo");
        let q = vec![
            mk_span(vec![mk_part(0, NamePartTag::UNSET, 3)], qsym.clone()),
            mk_span(vec![mk_part(1, NamePartTag::UNSET, 3)], qsym.clone()),
        ];
        let r = vec![mk_span(
            vec![mk_part(0, NamePartTag::UNSET, 3)],
            qsym.clone(),
        )];
        let edges = build_candidate_edges(&q, &r);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].qparts, vec![0]); // first qspan wins
    }

    #[test]
    fn initial_both_multichar_rejected() {
        let s = sym(SymbolCategory::INITIAL, "j");
        let q = vec![mk_span(vec![mk_part(0, NamePartTag::UNSET, 4)], s.clone())];
        let r = vec![mk_span(vec![mk_part(0, NamePartTag::UNSET, 4)], s.clone())];
        let edges = build_candidate_edges(&q, &r);
        assert!(
            edges.is_empty(),
            "INITIAL with both sides multi-char must be rejected"
        );
    }

    #[test]
    fn initial_one_single_char_accepted() {
        let s = sym(SymbolCategory::INITIAL, "j");
        let q = vec![mk_span(vec![mk_part(0, NamePartTag::UNSET, 1)], s.clone())];
        let r = vec![mk_span(vec![mk_part(0, NamePartTag::UNSET, 4)], s.clone())];
        let edges = build_candidate_edges(&q, &r);
        assert_eq!(edges.len(), 1);
    }

    #[test]
    fn name_tag_cartesian_rejects_cross_side() {
        let s = sym(SymbolCategory::NAME, "QFoo");
        let q = vec![mk_span(
            vec![
                mk_part(0, NamePartTag::GIVEN, 3),
                mk_part(1, NamePartTag::FAMILY, 3),
            ],
            s.clone(),
        )];
        let r = vec![mk_span(
            vec![
                mk_part(0, NamePartTag::GIVEN, 3),
                mk_part(1, NamePartTag::FAMILY, 3),
            ],
            s.clone(),
        )];
        // Cartesian check would find GIVEN vs FAMILY pair and fail.
        let edges = build_candidate_edges(&q, &r);
        assert!(edges.is_empty());
    }

    #[test]
    fn subsumption_drops_shorter_same_category() {
        let name_sym = SymbolCategory::NAME;
        let short = Edge {
            qmask: 1 << 1,
            rmask: 1 << 1,
            qparts: vec![1],
            rparts: vec![1],
            symbol: sym(name_sym, "QShort"),
        };
        let long = Edge {
            qmask: (1 << 1) | (1 << 2),
            rmask: (1 << 1) | (1 << 2),
            qparts: vec![1, 2],
            rparts: vec![1, 2],
            symbol: sym(name_sym, "QLong"),
        };
        let mut edges = vec![short, long];
        prune_subsumed(&mut edges);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].symbol.id.as_ref(), "QLong");
    }

    #[test]
    fn subsumption_preserves_cross_category() {
        let short_sym = Edge {
            qmask: 1 << 1,
            rmask: 1 << 1,
            qparts: vec![1],
            rparts: vec![1],
            symbol: sym(SymbolCategory::SYMBOL, "van"),
        };
        let long_name = Edge {
            qmask: (1 << 1) | (1 << 2),
            rmask: (1 << 1) | (1 << 2),
            qparts: vec![1, 2],
            rparts: vec![1, 2],
            symbol: sym(SymbolCategory::NAME, "QvanDijk"),
        };
        let mut edges = vec![short_sym, long_name];
        prune_subsumed(&mut edges);
        assert_eq!(edges.len(), 2, "cross-category edge must survive");
    }

    #[test]
    fn dfs_empty_edges_returns_empty_pairing() {
        let coverings = enumerate_coverings(&[]);
        assert_eq!(coverings, vec![Vec::<usize>::new()]);
    }

    #[test]
    fn dfs_two_disjoint_edges_single_covering() {
        let edges = vec![
            Edge {
                qmask: 1 << 0,
                rmask: 1 << 0,
                qparts: vec![0],
                rparts: vec![0],
                symbol: sym(SymbolCategory::NAME, "QA"),
            },
            Edge {
                qmask: 1 << 1,
                rmask: 1 << 1,
                qparts: vec![1],
                rparts: vec![1],
                symbol: sym(SymbolCategory::NAME, "QB"),
            },
        ];
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings.len(), 2); // empty + full
        assert_eq!(coverings[1], vec![0, 1]);
    }

    #[test]
    fn dfs_cross_category_on_same_parts_emits_two() {
        let edges = vec![
            Edge {
                qmask: 1 << 0,
                rmask: 1 << 0,
                qparts: vec![0],
                rparts: vec![0],
                symbol: sym(SymbolCategory::NAME, "Qvan"),
            },
            Edge {
                qmask: 1 << 0,
                rmask: 1 << 0,
                qparts: vec![0],
                rparts: vec![0],
                symbol: sym(SymbolCategory::SYMBOL, "van"),
            },
        ];
        let coverings = enumerate_coverings(&edges);
        // empty + NAME-only + SYMBOL-only
        assert_eq!(coverings.len(), 3);
    }
}
