//! Symbol pairing — align the symbol spans of two [`Name`]s into
//! coverage-maximal pairings.
//!
//! When a matcher has two tagger-annotated names and wants to
//! skip string-distance work on the tokens the tagger has already
//! explained (shared Wikidata QIDs on person names, matching
//! legal-form symbols, cross-script alias links), it calls
//! [`py_pair_symbols`]. The returned pairings carry the symbol
//! edges; the matcher runs Levenshtein on the remainder.
//!
//! Each returned pairing is a non-conflicting set of [`Alignment`]s
//! whose joint coverage is maximal within its scoring-equivalence
//! class. Each `Alignment` has `symbol = Some(_)` (the shared
//! `Symbol` both sides carry) and a placeholder `score = 1.0` —
//! consumers are expected to override the score with a per-category
//! default (e.g. `NAME → 0.9`, `NICK → 0.6`) at the point they wrap
//! the alignment for scoring. The empty pairing is a fallback
//! emitted only when no symbol evidence is available on either side
//! — callers that iterate can rely on the list being non-empty.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use pyo3::prelude::*;
use pyo3::types::{PyList, PyTuple};

use crate::names::alignment::Alignment;
use crate::names::name::Name;
use crate::names::part::{NamePart, Span};
use crate::names::symbol::{Symbol, SymbolCategory};
use crate::names::tag::NamePartTag;

/// Upper bound on name-part count. Inputs beyond this short-circuit
/// to the empty-only fallback; bitmask-based coverage tracking needs
/// to fit in a `u64`.
const MAX_PARTS: usize = 64;

/// Bundled output of [`collect_spans`].
type SpansAndSymbols = (Vec<SpanInfo>, HashMap<Symbol, Py<Symbol>>);

/// Per-part fields the pairing algorithm reads: tag (for
/// NAME/NICK compatibility checks) and character length (for
/// the INITIAL single-char rule).
#[derive(Clone, Debug)]
struct PartInfo {
    index: u32,
    tag: NamePartTag,
    char_len: usize,
}

/// One tagger-attached span flattened for pairing-side use.
#[derive(Clone, Debug)]
struct SpanInfo {
    parts: Vec<PartInfo>,
    mask: u64,
    min_idx: u32,
    symbol: Symbol,
}

/// A candidate edge — a tentative binding of one query span to
/// one result span. Coverage lives in the bitmasks;
/// [`mask_to_part_vec`] expands them to index lists at output.
#[derive(Clone, Debug)]
struct Edge {
    qmask: u64,
    rmask: u64,
    symbol: Symbol,
}

/// Flatten a [`Name`]'s tagger spans into pairing-ready
/// [`SpanInfo`] records, and index the Python `Symbol` objects
/// by their Rust-side equivalents for zero-alloc reuse at output.
/// Output is sorted by span start position.
fn collect_spans(py: Python<'_>, name: &Name) -> PyResult<SpansAndSymbols> {
    let spans_list = name.spans.bind(py);
    let mut out: Vec<SpanInfo> = Vec::with_capacity(spans_list.len());
    let mut sym_py: HashMap<Symbol, Py<Symbol>> = HashMap::new();
    for item in spans_list.iter() {
        let span = item.cast::<Span>()?.borrow();
        let parts_tuple = span.parts.bind(py);
        let mut parts: Vec<PartInfo> = Vec::with_capacity(parts_tuple.len());
        let mut mask: u64 = 0;
        let mut min_idx: u32 = u32::MAX;
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
            if info.index < min_idx {
                min_idx = info.index;
            }
            parts.push(info);
        }
        let symbol: Symbol = span.symbol.bind(py).extract()?;
        sym_py
            .entry(symbol.clone())
            .or_insert_with(|| span.symbol.clone_ref(py));
        out.push(SpanInfo {
            parts,
            mask,
            min_idx,
            symbol,
        });
    }
    out.sort_by_key(|s| s.min_idx);
    Ok((out, sym_py))
}

/// Per-edge compatibility filter. `INITIAL` edges require at
/// least one single-character part (a `J` ↔ `John` pairing makes
/// sense; `Jan` ↔ `John` through an `INITIAL:j` symbol doesn't).
/// `NAME` and `NICK` edges require every qspan part to be
/// [`NamePartTag::can_match`]-compatible with every rspan part,
/// so a span mixing GIVEN and FAMILY parts can't pair with one
/// that swaps them.
fn spans_can_pair(qspan: &SpanInfo, rspan: &SpanInfo) -> bool {
    match qspan.symbol.category {
        SymbolCategory::INITIAL => {
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

/// Build candidate edges by greedy-binding query spans to result
/// spans for each shared [`Symbol`]. When a symbol occurs N times
/// on one side and M times on the other, this yields `min(N, M)`
/// edges — not N × M — because instances of the same symbol are
/// interchangeable for scoring.
///
/// Both sides are bound widest-first (popcount-descending on the
/// span mask). When the AC tagger produces overlapping same-symbol
/// spans on one side — e.g. `[pla]` and `[pla, china]` both tagged
/// `DOMAIN:PLA` against the phrase `"PLA China"` — the narrower
/// span is strictly worse evidence and we want the wider one to
/// claim the r-side first. Ties fall back to insertion order, so
/// disjoint duplicates (`[john]`, `[john]`) still bind in their
/// natural `min_idx` order.
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
        let mut q_ordered: Vec<usize> = q_indices.clone();
        q_ordered.sort_by_key(|&i| std::cmp::Reverse(q_spans[i].mask.count_ones()));
        let mut r_ordered: Vec<usize> = r_indices.clone();
        r_ordered.sort_by_key(|&i| std::cmp::Reverse(r_spans[i].mask.count_ones()));
        let mut r_taken: Vec<bool> = vec![false; r_ordered.len()];
        for &qi in &q_ordered {
            let qspan = &q_spans[qi];
            for (r_pos, &ri) in r_ordered.iter().enumerate() {
                if r_taken[r_pos] {
                    continue;
                }
                let rspan = &r_spans[ri];
                if spans_can_pair(qspan, rspan) {
                    r_taken[r_pos] = true;
                    edges.push(Edge {
                        qmask: qspan.mask,
                        rmask: rspan.mask,
                        symbol: sym.clone(),
                    });
                    break;
                }
            }
        }
    }
    edges
}

/// Drop edges strictly dominated by another edge in the same
/// category. A compound `NAME:QvanDijk` covering `[van, Dijk]`
/// absorbs a shorter `NAME:Qvan` covering `[van]` — the matcher
/// would score the compound as the more specific signal anyway.
/// Cross-category edges (e.g. `SYMBOL:van` alongside the compound
/// NAME) are untouched.
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

/// Collapse edges sharing `(qmask, rmask, category)`. Such edges
/// differ only in `symbol.id` — the DFS coverage dedup at the leaf
/// keys on `(qmask, rmask, sorted_categories)` and already drops
/// the redundant ones, but only after walking every selection path
/// that reaches them. Pre-collapsing here cuts the DFS branching
/// factor proportionally; on the `Isa Bin Tarif Al Bin Ali` /
/// `Shaikh …` repro it's 27 → 7 edges, ~7290 → ~32 leaves.
///
/// Keeps the alphabetically-smallest `symbol.id` per class as the
/// canonical edge for deterministic output.
fn dedupe_equivalent_edges(edges: &mut Vec<Edge>) {
    if edges.len() < 2 {
        return;
    }
    let mut by_class: HashMap<(u64, u64, SymbolCategory), Edge> = HashMap::new();
    for edge in edges.drain(..) {
        let key = (edge.qmask, edge.rmask, edge.symbol.category);
        let replace = match by_class.get(&key) {
            Some(existing) => edge.symbol.id < existing.symbol.id,
            None => true,
        };
        if replace {
            by_class.insert(key, edge);
        }
    }
    edges.extend(by_class.into_values());
}

/// Deterministic sort key: earlier-in-name edges first, ties
/// broken by category and symbol id.
fn edge_sort_key(e: &Edge) -> (u32, u32, SymbolCategory, Arc<str>) {
    (
        e.qmask.trailing_zeros(),
        e.rmask.trailing_zeros(),
        e.symbol.category,
        e.symbol.id.clone(),
    )
}

/// Enumerate maximal non-conflicting edge selections, one per
/// `(qmask, rmask, sorted categories)` equivalence class.
///
/// Emits the empty selection only when no candidate edges exist
/// — once any symbol evidence is available, we commit to it and
/// don't return an empty-covering alternative that would compete
/// with the symbol-matched pairings in downstream scoring.
fn enumerate_coverings(edges: &[Edge]) -> Vec<Vec<usize>> {
    let mut results: Vec<Vec<usize>> = Vec::new();
    let mut seen: HashSet<(u64, u64, Vec<SymbolCategory>)> = HashSet::new();

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
    seen: &mut HashSet<(u64, u64, Vec<SymbolCategory>)>,
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
        let mut cats: Vec<SymbolCategory> =
            picked.iter().map(|&j| edges[j].symbol.category).collect();
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

/// The degenerate-case output: a list with one empty pairing.
/// Used when input guards trip (> 64 parts, missing spans) so
/// callers get a well-formed but non-matched result they can
/// fall through to full Levenshtein on.
fn empty_output(py: Python<'_>) -> PyResult<Py<PyList>> {
    let empty_tuple = PyTuple::empty(py);
    let list = PyList::new(py, [empty_tuple])?;
    Ok(list.unbind())
}

/// Expand a part-index bitmask to an ascending index vector.
fn mask_to_part_vec(mut mask: u64) -> Vec<u32> {
    let mut out: Vec<u32> = Vec::with_capacity(mask.count_ones() as usize);
    while mask != 0 {
        out.push(mask.trailing_zeros());
        mask &= mask - 1;
    }
    out
}

/// Convert a coverage selection into a Python tuple of
/// [`Alignment`] instances. Re-uses the tagger's `Py<Symbol>`
/// objects so two alignments carrying the same symbol compare
/// as `is`-equal on the Python side. Resolves part-index
/// bitmasks against the input names' `parts` tuples to fill
/// each alignment's `qps` / `rps` with the actual `NamePart`
/// references.
fn build_pairing(
    py: Python<'_>,
    edges: &[Edge],
    indices: &[usize],
    q_symbols: &HashMap<Symbol, Py<Symbol>>,
    query_parts: &Bound<'_, PyTuple>,
    result_parts: &Bound<'_, PyTuple>,
) -> PyResult<Py<PyTuple>> {
    let mut edge_objs: Vec<Py<Alignment>> = Vec::with_capacity(indices.len());
    for &i in indices {
        let e = &edges[i];
        let qparts: Vec<Py<NamePart>> = mask_to_part_vec(e.qmask)
            .into_iter()
            .map(|idx| -> PyResult<Py<NamePart>> {
                Ok(query_parts
                    .get_item(idx as usize)?
                    .cast::<NamePart>()?
                    .clone()
                    .unbind())
            })
            .collect::<PyResult<_>>()?;
        let rparts: Vec<Py<NamePart>> = mask_to_part_vec(e.rmask)
            .into_iter()
            .map(|idx| -> PyResult<Py<NamePart>> {
                Ok(result_parts
                    .get_item(idx as usize)?
                    .cast::<NamePart>()?
                    .clone()
                    .unbind())
            })
            .collect::<PyResult<_>>()?;
        // Every edge.symbol came from a query span, so q_symbols
        // has it by construction.
        let symbol_py = q_symbols
            .get(&e.symbol)
            .expect("edge.symbol must come from q_symbols")
            .clone_ref(py);
        let alignment = Alignment::build(py, qparts, rparts, Some(symbol_py), 1.0)?;
        edge_objs.push(Py::new(py, alignment)?);
    }
    Ok(PyTuple::new(py, &edge_objs)?.unbind())
}

/// Align the symbol spans of two [`Name`]s into coverage-maximal
/// pairings.
///
/// Each returned pairing is a tuple of non-conflicting
/// [`Alignment`]s; edges within a pairing cover disjoint parts on
/// each side. Each `Alignment` has `symbol = Some(_)` and a
/// placeholder `score = 1.0` — consumers should override the
/// score with a per-category default before composing the pairing
/// total. Pairings are distinguished by their coverage and
/// category multiset — two pairings that cover the same parts
/// with the same category mix are collapsed to one. Distinct
/// category choices on the same parts (e.g. a token carrying both
/// `NAME:Qvan` and `SYMBOL:van`) surface as separate pairings.
///
/// Returns `[()]` (a single empty pairing) when either name has
/// more than 64 parts, when either name has no tagger spans, or
/// when no symbol is shared between the two sides.
#[pyfunction]
#[pyo3(name = "pair_symbols")]
pub fn py_pair_symbols(
    py: Python<'_>,
    query: PyRef<'_, Name>,
    result: PyRef<'_, Name>,
) -> PyResult<Py<PyList>> {
    let query_parts = query.parts.bind(py);
    let result_parts = result.parts.bind(py);
    let q_parts_len = query_parts.len();
    let r_parts_len = result_parts.len();
    if q_parts_len > MAX_PARTS || r_parts_len > MAX_PARTS {
        return empty_output(py);
    }

    let (q_spans, q_symbols) = collect_spans(py, &query)?;
    let (r_spans, _r_symbols) = collect_spans(py, &result)?;
    if q_spans.is_empty() || r_spans.is_empty() {
        return empty_output(py);
    }

    let mut edges = build_candidate_edges(&q_spans, &r_spans);
    prune_subsumed(&mut edges);
    dedupe_equivalent_edges(&mut edges);
    edges.sort_by_cached_key(edge_sort_key);

    let coverings = enumerate_coverings(&edges);

    let qp_ref = &query_parts;
    let rp_ref = &result_parts;
    let pairings: Vec<Py<PyTuple>> = coverings
        .iter()
        .map(|indices| build_pairing(py, &edges, indices, &q_symbols, qp_ref, rp_ref))
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
        let mut min_idx: u32 = u32::MAX;
        for p in &parts {
            mask |= 1u64 << p.index;
            if p.index < min_idx {
                min_idx = p.index;
            }
        }
        SpanInfo {
            parts,
            mask,
            min_idx,
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
        assert_eq!(edges[0].qmask, 1 << 0);
        assert_eq!(edges[0].rmask, 1 << 0);
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
        // First qspan (index 0) wins the binding.
        assert_eq!(edges[0].qmask, 1 << 0);
    }

    #[test]
    fn overlapping_q_spans_bind_widest_first() {
        // The AC tagger emits overlapping same-symbol spans when
        // one alias is a prefix of another (e.g. "PLA" and
        // "PLA China" both map to DOMAIN:PLA against "PLA China").
        // The wider span must claim the lone r-side span; the
        // narrower one is strictly worse evidence and drops out.
        let sym_pla = sym(SymbolCategory::DOMAIN, "PLA");
        let q = vec![
            // Insertion order mirrors the AC tagger: shorter match
            // completes first, so the [pla]-only span arrives before
            // the [pla, china] span.
            mk_span(vec![mk_part(0, NamePartTag::UNSET, 3)], sym_pla.clone()),
            mk_span(
                vec![
                    mk_part(0, NamePartTag::UNSET, 3),
                    mk_part(1, NamePartTag::UNSET, 5),
                ],
                sym_pla.clone(),
            ),
        ];
        let r = vec![mk_span(
            vec![
                mk_part(0, NamePartTag::UNSET, 7),
                mk_part(1, NamePartTag::UNSET, 10),
                mk_part(2, NamePartTag::UNSET, 4),
            ],
            sym_pla.clone(),
        )];
        let edges = build_candidate_edges(&q, &r);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].qmask, 0b11, "wider q-span must win");
        assert_eq!(edges[0].rmask, 0b111);
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

    fn mk_edge(qmask: u64, rmask: u64, symbol: Symbol) -> Edge {
        Edge {
            qmask,
            rmask,
            symbol,
        }
    }

    #[test]
    fn subsumption_drops_shorter_same_category() {
        let cat = SymbolCategory::NAME;
        let mut edges = vec![
            mk_edge(1 << 1, 1 << 1, sym(cat, "QShort")),
            mk_edge((1 << 1) | (1 << 2), (1 << 1) | (1 << 2), sym(cat, "QLong")),
        ];
        prune_subsumed(&mut edges);
        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0].symbol.id.as_ref(), "QLong");
    }

    #[test]
    fn subsumption_preserves_cross_category() {
        let mut edges = vec![
            mk_edge(1 << 1, 1 << 1, sym(SymbolCategory::SYMBOL, "van")),
            mk_edge(
                (1 << 1) | (1 << 2),
                (1 << 1) | (1 << 2),
                sym(SymbolCategory::NAME, "QvanDijk"),
            ),
        ];
        prune_subsumed(&mut edges);
        assert_eq!(edges.len(), 2, "cross-category edge must survive");
    }

    #[test]
    fn dedupe_collapses_same_qrcat_keeps_smallest_id() {
        // Three edges sharing (qmask, rmask, NAME) and one cross-class
        // edge. Only the alphabetically-smallest id survives in the
        // NAME class; the cross-class edge is left alone.
        let mut edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "Q3")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "Q1")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "Q2")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::SYMBOL, "FOO")),
        ];
        dedupe_equivalent_edges(&mut edges);
        assert_eq!(edges.len(), 2);
        let kept: HashSet<(SymbolCategory, String)> = edges
            .iter()
            .map(|e| (e.symbol.category, e.symbol.id.to_string()))
            .collect();
        let expected: HashSet<(SymbolCategory, String)> = [
            (SymbolCategory::NAME, "Q1".to_string()),
            (SymbolCategory::SYMBOL, "FOO".to_string()),
        ]
        .into_iter()
        .collect();
        assert_eq!(kept, expected);
    }

    #[test]
    fn dedupe_preserves_distinct_masks() {
        // Same category, same id, but different qmasks → distinct
        // edges (each binds a different q-instance to its r-counterpart).
        let s = sym(SymbolCategory::NAME, "QBin");
        let mut edges = vec![
            mk_edge(1 << 1, 1 << 2, s.clone()),
            mk_edge(1 << 4, 1 << 5, s.clone()),
        ];
        dedupe_equivalent_edges(&mut edges);
        assert_eq!(edges.len(), 2, "distinct masks must not collapse");
    }

    #[test]
    fn dfs_empty_edges_returns_empty_pairing() {
        // No candidate edges → the empty covering is the only
        // emitted pairing (the fallback case).
        let coverings = enumerate_coverings(&[]);
        assert_eq!(coverings, vec![Vec::<usize>::new()]);
    }

    #[test]
    fn dfs_two_disjoint_edges_single_covering() {
        // Edges exist → empty covering is NOT emitted alongside.
        let edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "QA")),
            mk_edge(1 << 1, 1 << 1, sym(SymbolCategory::NAME, "QB")),
        ];
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings, vec![vec![0, 1]]);
    }

    #[test]
    fn dfs_cross_category_on_same_parts_emits_two() {
        // Two conflicting edges (same masks, different categories)
        // → NAME-only and SYMBOL-only coverings; no empty.
        let edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "Qvan")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::SYMBOL, "van")),
        ];
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings.len(), 2);
    }

    #[test]
    fn mask_to_part_vec_ascending() {
        assert_eq!(mask_to_part_vec(0), Vec::<u32>::new());
        assert_eq!(mask_to_part_vec(0b1011), vec![0, 1, 3]);
        assert_eq!(mask_to_part_vec(1u64 << 63), vec![63]);
    }
}
