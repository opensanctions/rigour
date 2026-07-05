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

/// Post-dedupe cap on candidate edges. Bounds every downstream
/// structure (conflict graph, components, enumeration) and lets
/// edge selections live in a `u64` bitset. When it binds — real
/// names produce single-digit edge counts, so only on adversarial
/// input — the widest-coverage edges are kept, dropping the weakest
/// evidence rather than all of it.
const MAX_EDGES: usize = 64;

/// Cap on emitted pairings. The corpus maximum on real name pairs
/// is 6; every emitted pairing costs the consumer a residue-distance
/// pass, so the cap is deliberately far below anything a genuine
/// name produces while bounding adversarial fan-out.
const MAX_PAIRINGS: usize = 32;

/// Cap on ranked alternatives kept per conflict component
/// (corpus maximum: 3). Lowest-coverage alternatives drop first.
const MAX_COMPONENT_ALTS: usize = 8;

/// Recursion-node budget for one component's maximal-selection
/// enumeration. On exhaustion the component degrades to its greedy
/// maximal selection — keeping symbol evidence rather than none.
const COMPONENT_NODE_BUDGET: usize = 4096;

/// Iteration budget for the cross-component cartesian product.
/// Guards the case where many combinations dedupe into few
/// equivalence classes and the product would spin without emitting.
const PRODUCT_ITER_BUDGET: usize = 4096;

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
/// differ only in `symbol.id`, which the selection-level
/// equivalence dedup ignores — pre-collapsing them here keeps the
/// conflict graph and per-component enumeration proportionally
/// smaller; on the `Isa Bin Tarif Al Bin Ali` / `Shaikh …` repro
/// it's 27 → 7 edges.
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
/// broken by category and symbol id. Uses the full masks — after
/// [`dedupe_equivalent_edges`] no two edges share
/// `(qmask, rmask, category)`, so this is a total order and the
/// sorted sequence is independent of the `HashMap` iteration
/// order in edge construction and dedupe. (Projecting the masks
/// to `trailing_zeros()` here used to collapse cross-bound
/// same-symbol edges into identical keys, leaking HashMap order
/// into the output.)
fn edge_sort_key(e: &Edge) -> (u64, u64, SymbolCategory, Arc<str>) {
    (e.qmask, e.rmask, e.symbol.category, e.symbol.id.clone())
}

/// Expand an edge-index bitset into an ascending index vector.
fn bitset_to_indices(mut sel: u64) -> Vec<usize> {
    let mut out: Vec<usize> = Vec::with_capacity(sel.count_ones() as usize);
    while sel != 0 {
        out.push(sel.trailing_zeros() as usize);
        sel &= sel - 1;
    }
    out
}

/// The scoring-equivalence class of an edge selection: joint part
/// coverage per side plus the sorted category multiset. Selections
/// in the same class are interchangeable for downstream scoring.
fn selection_class(edges: &[Edge], sel: u64) -> (u64, u64, Vec<SymbolCategory>) {
    let mut qcov: u64 = 0;
    let mut rcov: u64 = 0;
    let mut cats: Vec<SymbolCategory> = Vec::with_capacity(sel.count_ones() as usize);
    for v in bitset_to_indices(sel) {
        qcov |= edges[v].qmask;
        rcov |= edges[v].rmask;
        cats.push(edges[v].symbol.category);
    }
    cats.sort_unstable();
    (qcov, rcov, cats)
}

/// Enumerate the maximal cliques of the compatibility graph
/// restricted to `members` — i.e. the maximal non-conflicting edge
/// selections within one conflict component — via Bron–Kerbosch
/// with pivoting. Returns `false` when the node budget runs out,
/// signalling the caller to degrade the component to its greedy
/// selection.
fn bron_kerbosch(
    compat: &[u64],
    members: u64,
    r: u64,
    mut p: u64,
    mut x: u64,
    out: &mut Vec<u64>,
    budget: &mut usize,
) -> bool {
    if *budget == 0 {
        return false;
    }
    *budget -= 1;
    if p == 0 && x == 0 {
        out.push(r);
        return true;
    }
    // Pivot on the vertex with the most candidates among its
    // compatible set — on dense compatibility (the common,
    // few-conflicts case) this collapses the branching to a
    // single path.
    let mut pivot: usize = 0;
    let mut best: i64 = -1;
    let mut pux = p | x;
    while pux != 0 {
        let u = pux.trailing_zeros() as usize;
        pux &= pux - 1;
        let cnt = (p & compat[u] & members).count_ones() as i64;
        if cnt > best {
            best = cnt;
            pivot = u;
        }
    }
    let mut cand = p & !(compat[pivot] & members);
    while cand != 0 {
        let v = cand.trailing_zeros() as usize;
        cand &= cand - 1;
        let vbit = 1u64 << v;
        let nv = compat[v] & members;
        if !bron_kerbosch(compat, members, r | vbit, p & nv, x & nv, out, budget) {
            return false;
        }
        p &= !vbit;
        x |= vbit;
    }
    true
}

/// One maximal selection for a component, built greedily in edge
/// sort order. Fallback for components whose exhaustive enumeration
/// blows the node budget — commits to some symbol evidence rather
/// than dropping the component.
fn greedy_selection(edges: &[Edge], members: u64) -> u64 {
    let mut sel: u64 = 0;
    let mut qcov: u64 = 0;
    let mut rcov: u64 = 0;
    for v in bitset_to_indices(members) {
        if (edges[v].qmask & qcov) == 0 && (edges[v].rmask & rcov) == 0 {
            sel |= 1u64 << v;
            qcov |= edges[v].qmask;
            rcov |= edges[v].rmask;
        }
    }
    sel
}

/// Best-first rank key for a component selection: joint coverage
/// popcount descending, then full masks, category multiset and the
/// selection bitset itself for a deterministic total order.
type SelectionRank = (std::cmp::Reverse<u32>, u64, u64, Vec<SymbolCategory>, u64);

/// The ranked, deduped maximal selections of one conflict
/// component, best (highest joint coverage) first, truncated to
/// [`MAX_COMPONENT_ALTS`].
fn component_alternatives(edges: &[Edge], compat: &[u64], members: u64, budget: usize) -> Vec<u64> {
    if members.count_ones() == 1 {
        return vec![members];
    }
    let mut selections: Vec<u64> = Vec::new();
    let mut node_budget = budget;
    let complete = bron_kerbosch(
        compat,
        members,
        0,
        members,
        0,
        &mut selections,
        &mut node_budget,
    );
    if !complete {
        return vec![greedy_selection(edges, members)];
    }
    // Rank best-first: joint coverage popcount descending, then a
    // full-mask key for a deterministic total order. Dedupe by
    // scoring-equivalence class, keeping the best-ranked selection
    // per class.
    let mut keyed: Vec<SelectionRank> = selections
        .into_iter()
        .map(|sel| {
            let (qcov, rcov, cats) = selection_class(edges, sel);
            (
                std::cmp::Reverse(qcov.count_ones() + rcov.count_ones()),
                qcov,
                rcov,
                cats,
                sel,
            )
        })
        .collect();
    keyed.sort();
    let mut seen: HashSet<(u64, u64, Vec<SymbolCategory>)> = HashSet::new();
    let mut out: Vec<u64> = Vec::new();
    for (_, qcov, rcov, cats, sel) in keyed {
        if seen.insert((qcov, rcov, cats)) {
            out.push(sel);
            if out.len() >= MAX_COMPONENT_ALTS {
                break;
            }
        }
    }
    out
}

/// Enumerate maximal non-conflicting edge selections, one per
/// `(qmask, rmask, sorted categories)` equivalence class, best
/// coverage first.
///
/// Edges conflict iff their part coverage overlaps on either side.
/// A maximal global selection is the union of one maximal selection
/// per connected component of the conflict graph, so enumeration
/// factorizes: isolated edges are forced into every selection,
/// genuine alternatives are enumerated per component
/// (Bron–Kerbosch over the component's compatibility graph), and
/// the cartesian product across components is deduped by the global
/// equivalence class — the global category-multiset key collapses
/// cross-component category swaps on identical masks, so the
/// product alone would over-emit.
///
/// Bounded on adversarial input by [`MAX_COMPONENT_ALTS`],
/// [`MAX_PAIRINGS`], [`COMPONENT_NODE_BUDGET`] and
/// [`PRODUCT_ITER_BUDGET`]; all truncation is deterministic and
/// drops lowest-coverage alternatives first. Emits the empty
/// selection only when no candidate edges exist — once any symbol
/// evidence is available, we commit to it and don't return an
/// empty-covering alternative that would compete with the
/// symbol-matched pairings in downstream scoring.
fn enumerate_coverings(edges: &[Edge]) -> Vec<Vec<usize>> {
    let n = edges.len();
    if n == 0 {
        return vec![Vec::new()];
    }
    debug_assert!(
        n <= MAX_EDGES,
        "edge cap must be applied before enumeration"
    );

    // Pairwise compatibility bitsets (self-bit excluded).
    let mut compat: Vec<u64> = vec![0; n];
    for i in 0..n {
        for j in (i + 1)..n {
            let conflict =
                (edges[i].qmask & edges[j].qmask) != 0 || (edges[i].rmask & edges[j].rmask) != 0;
            if !conflict {
                compat[i] |= 1u64 << j;
                compat[j] |= 1u64 << i;
            }
        }
    }
    let full: u64 = if n == 64 { u64::MAX } else { (1u64 << n) - 1 };

    // Connected components of the conflict graph, discovered in
    // ascending edge order so component order is deterministic.
    let mut assigned: u64 = 0;
    let mut alt_lists: Vec<Vec<u64>> = Vec::new();
    for start in 0..n {
        if assigned & (1u64 << start) != 0 {
            continue;
        }
        let mut members: u64 = 1u64 << start;
        let mut frontier: u64 = members;
        while frontier != 0 {
            let mut next: u64 = 0;
            for v in bitset_to_indices(frontier) {
                let conflicts = full & !compat[v] & !(1u64 << v);
                next |= conflicts & !members;
            }
            members |= next;
            frontier = next;
        }
        assigned |= members;
        alt_lists.push(component_alternatives(
            edges,
            &compat,
            members,
            COMPONENT_NODE_BUDGET,
        ));
    }

    // Cartesian product across components in mixed-radix order —
    // the first combination is every component's best alternative.
    // Dedupe by global equivalence class while emitting.
    let mut results: Vec<Vec<usize>> = Vec::new();
    let mut seen: HashSet<(u64, u64, Vec<SymbolCategory>)> = HashSet::new();
    let mut idx: Vec<usize> = vec![0; alt_lists.len()];
    let mut iterations = 0;
    loop {
        let mut sel: u64 = 0;
        for (c, list) in alt_lists.iter().enumerate() {
            sel |= list[idx[c]];
        }
        let class = selection_class(edges, sel);
        if seen.insert(class) {
            results.push(bitset_to_indices(sel));
            if results.len() >= MAX_PAIRINGS {
                break;
            }
        }
        iterations += 1;
        if iterations >= PRODUCT_ITER_BUDGET {
            break;
        }
        // Advance the mixed-radix counter; done when it wraps.
        let mut c = alt_lists.len();
        let mut advanced = false;
        while c > 0 {
            c -= 1;
            idx[c] += 1;
            if idx[c] < alt_lists[c].len() {
                advanced = true;
                break;
            }
            idx[c] = 0;
        }
        if !advanced {
            break;
        }
    }
    results
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
        let alignment = Alignment::build(py, qparts, rparts, Some(symbol_py), 1.0, 1.0)?;
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
/// At most 32 pairings are returned, ranked by joint coverage;
/// on adversarial inputs whose alternative structure exceeds
/// internal budgets, lowest-coverage alternatives are dropped
/// deterministically. Real name pairs produce single-digit
/// pairing counts and are never truncated.
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
    if edges.len() > MAX_EDGES {
        // Keep the widest-coverage edges; deterministic tie-break
        // on the full sort key. Only reachable on adversarial
        // input — real names produce single-digit edge counts.
        edges.sort_by_cached_key(|e| {
            (
                std::cmp::Reverse(e.qmask.count_ones() + e.rmask.count_ones()),
                e.qmask,
                e.rmask,
                e.symbol.category,
                e.symbol.id.clone(),
            )
        });
        edges.truncate(MAX_EDGES);
    }
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
    fn edge_sort_key_total_order_on_cross_bound_masks() {
        // Cross-bound same-symbol edges — e.g. the greedy binder
        // forced into (q=0b01, r=0b11) / (q=0b11, r=0b01) by a
        // spans_can_pair rejection — share the lowest set bit on
        // both sides. A trailing_zeros() projection keys them
        // identically, so their sorted order (and hence the
        // enumeration order and output) would follow pre-sort
        // HashMap order. The full-mask key must distinguish them
        // and yield the same sequence from either permutation.
        let s = sym(SymbolCategory::INITIAL, "j");
        let a = mk_edge(0b01, 0b11, s.clone());
        let b = mk_edge(0b11, 0b01, s.clone());
        assert_ne!(edge_sort_key(&a), edge_sort_key(&b));
        let mut fwd = vec![a.clone(), b.clone()];
        let mut rev = vec![b, a];
        fwd.sort_by_cached_key(edge_sort_key);
        rev.sort_by_cached_key(edge_sort_key);
        let order = |v: &[Edge]| v.iter().map(|e| (e.qmask, e.rmask)).collect::<Vec<_>>();
        assert_eq!(order(&fwd), order(&rev));
    }

    /// Every covering must be internally disjoint on both sides and
    /// maximal — no un-picked edge compatible with it.
    fn assert_valid_coverings(edges: &[Edge], coverings: &[Vec<usize>]) {
        for covering in coverings {
            let mut qcov: u64 = 0;
            let mut rcov: u64 = 0;
            for &i in covering {
                assert_eq!(edges[i].qmask & qcov, 0, "q-side overlap in covering");
                assert_eq!(edges[i].rmask & rcov, 0, "r-side overlap in covering");
                qcov |= edges[i].qmask;
                rcov |= edges[i].rmask;
            }
            for (j, edge) in edges.iter().enumerate() {
                if covering.contains(&j) {
                    continue;
                }
                assert!(
                    (edge.qmask & qcov) != 0 || (edge.rmask & rcov) != 0,
                    "covering not maximal: edge {j} is compatible"
                );
            }
        }
    }

    #[test]
    fn coverings_empty_edges_returns_empty_pairing() {
        // No candidate edges → the empty covering is the only
        // emitted pairing (the fallback case).
        let coverings = enumerate_coverings(&[]);
        assert_eq!(coverings, vec![Vec::<usize>::new()]);
    }

    #[test]
    fn coverings_two_disjoint_edges_single_covering() {
        // Edges exist → empty covering is NOT emitted alongside.
        let edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "QA")),
            mk_edge(1 << 1, 1 << 1, sym(SymbolCategory::NAME, "QB")),
        ];
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings, vec![vec![0, 1]]);
    }

    #[test]
    fn coverings_cross_category_on_same_parts_emits_two() {
        // Two conflicting edges (same masks, different categories)
        // → NAME-only and SYMBOL-only coverings; no empty.
        let edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "Qvan")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::SYMBOL, "van")),
        ];
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings.len(), 2);
        assert_valid_coverings(&edges, &coverings);
    }

    #[test]
    fn coverings_many_disjoint_edges_single_pass() {
        // The common case: pairwise-disjoint edges. Every edge is
        // an isolated conflict component and forced into the one
        // maximal selection. The pre-rework DFS visited 2^E subsets
        // here — at E = 40 that was ~10^12 leaf visits; this must
        // complete instantly with exactly one covering.
        let edges: Vec<Edge> = (0..40)
            .map(|i| {
                mk_edge(
                    1u64 << i,
                    1u64 << i,
                    sym(SymbolCategory::NAME, &format!("Q{i:02}")),
                )
            })
            .collect();
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings, vec![(0..40).collect::<Vec<usize>>()]);
    }

    #[test]
    fn coverings_cross_component_swaps_dedupe_globally() {
        // Two components, each offering a NAME/SYMBOL choice on
        // identical masks. The per-component product yields 4
        // combinations, but (NAME, SYMBOL) and (SYMBOL, NAME) share
        // the global category multiset on the same coverage — the
        // final global dedup must collapse them to 3 pairings
        // (mirrors the bin/ben corpus cases).
        let edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "QA")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::SYMBOL, "SA")),
            mk_edge(1 << 1, 1 << 1, sym(SymbolCategory::NAME, "QB")),
            mk_edge(1 << 1, 1 << 1, sym(SymbolCategory::SYMBOL, "SB")),
        ];
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings.len(), 3);
        assert_valid_coverings(&edges, &coverings);
    }

    #[test]
    fn coverings_respect_pairing_cap_best_first() {
        // Six components, each with two alternatives of distinct
        // coverage → 64 distinct equivalence classes. Output is
        // capped at MAX_PAIRINGS, and the first covering is every
        // component's best (widest-coverage) alternative.
        let mut edges: Vec<Edge> = Vec::new();
        for c in 0..6u32 {
            let narrow = 1u64 << (2 * c);
            let wide = narrow | (1u64 << (2 * c + 1));
            edges.push(mk_edge(narrow, narrow, sym(SymbolCategory::NAME, "QN")));
            edges.push(mk_edge(wide, narrow, sym(SymbolCategory::NAME, "QW")));
        }
        let coverings = enumerate_coverings(&edges);
        assert_eq!(coverings.len(), MAX_PAIRINGS);
        assert_valid_coverings(&edges, &coverings);
        // Odd indices are the wide alternatives.
        assert_eq!(coverings[0], vec![1, 3, 5, 7, 9, 11]);
    }

    #[test]
    fn component_budget_exhaustion_degrades_to_greedy() {
        // With a starved node budget, a component's enumeration
        // falls back to its single greedy maximal selection instead
        // of hanging or dropping the component.
        let edges = vec![
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::NAME, "QA")),
            mk_edge(1 << 0, 1 << 0, sym(SymbolCategory::SYMBOL, "SA")),
        ];
        let mut compat: Vec<u64> = vec![0; 2];
        // Edges conflict, so compat stays empty on both.
        compat[0] = 0;
        compat[1] = 0;
        let alts = component_alternatives(&edges, &compat, 0b11, 1);
        assert_eq!(alts, vec![greedy_selection(&edges, 0b11)]);
        assert_eq!(alts[0], 0b01, "greedy takes the first sorted edge");
    }

    #[test]
    fn mask_to_part_vec_ascending() {
        assert_eq!(mask_to_part_vec(0), Vec::<u32>::new());
        assert_eq!(mask_to_part_vec(0b1011), vec![0, 1, 3]);
        assert_eq!(mask_to_part_vec(1u64 << 63), vec![63]);
    }
}
