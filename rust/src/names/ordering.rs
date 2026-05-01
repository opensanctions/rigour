//! Align the name parts of two person names so that corresponding
//! tokens end up at the same position — essential for matcher-side
//! per-index similarity scoring when the two sides present their
//! parts in different orders or tokenisations.
//!
//! Behaviour pinned by `tests/names/test_ordering.py`.
//!
//! ## Invariants
//!
//! * **All-UNSET input is the primary regime.** Real-world data
//!   rarely carries per-part tags; alignment has to work on
//!   untagged input via fuzzy scoring and packing alone. Tag-aware
//!   pair-gating is a refinement, not a precondition.
//! * **Deterministic.** Same input produces the same output on
//!   every call — no hash-map iteration or hidden state.
//! * **Stable under ties.** Equal-scoring pairs are decided by
//!   input order: a length-descending **stable** sort of each
//!   side plus a left-major product walk gives the same winner
//!   every time. Matters because the all-UNSET regime produces
//!   ties as the common case.
//! * **Score floor of 0.3.** Pairs below it don't align — guards
//!   against "John" pairing with "Xyz" just because the greedy
//!   loop needs a match.
//! * **Packing handles tokenisation differences.** A long token
//!   ("alsabah") aligns with shorter parts ("al" + "sabah") by
//!   packing them together on the opposite side. Each candidate
//!   for packing is gated on `NamePartTag::can_match` against the
//!   anchor's tag.
//! * **Nothing-aligned fallback.** When no pair scores above the
//!   floor, both sides come back via `tag_sort_parts` instead of
//!   interleaved.
//! * **Empty-left short-circuits** to `([], tag_sort(right))`.
//!   Empty-right falls through to the nothing-aligned fallback.
//! * **Comparable-based**, not form-based — surface variations
//!   (spacing, commas, diacritics) normalise through
//!   `NamePart.comparable` before scoring.
//! * **Person-specific.** ORG / ENT / OBJ names use
//!   `tag_sort_parts` directly; this function only handles PER.

use pyo3::prelude::*;

use crate::names::part::{NamePart, tag_sort_parts};
use crate::names::tag::NamePartTag;
use crate::text::distance::damerau_levenshtein_cutoff;

/// Minimum similarity score for a candidate pair to register as a
/// match. Pinned by `test_align_similarity_floor`.
const SCORE_FLOOR: f64 = 0.3;

/// Cheap per-part snapshot, built once at entry so the scoring loop
/// doesn't re-borrow `Py<NamePart>` per iteration.
struct PartView {
    origin: usize,
    form_len: usize,
    comparable: String,
    comparable_len: usize,
    tag: NamePartTag,
}

fn extract_views(py: Python<'_>, parts: &[Py<NamePart>]) -> Vec<PartView> {
    parts
        .iter()
        .enumerate()
        .map(|(origin, p)| {
            let b = p.bind(py).borrow();
            let comparable = b.comparable_str().to_string();
            let comparable_len = comparable.chars().count();
            let form_len = b.form_str().chars().count();
            PartView {
                origin,
                form_len,
                comparable,
                comparable_len,
                tag: b.tag,
            }
        })
        .collect()
}

/// Similarity score between two comparable strings with the 0.3
/// floor applied. Returns 0.0 when the floor kicks in so callers
/// can compare with plain `>`.
fn score(a: &str, a_len: usize, b: &str, b_len: usize) -> f64 {
    if a == b {
        return 1.0;
    }
    let max_len = a_len.max(b_len);
    if max_len == 0 {
        return 1.0;
    }
    // score = 1 - d/max_len ≥ 0.3 ⇔ d ≤ floor(0.7 * max_len).
    let cutoff = (max_len * 7) / 10;
    let d = damerau_levenshtein_cutoff(a, b, cutoff);
    if d > cutoff {
        return 0.0;
    }
    let s = 1.0 - (d as f64 / max_len as f64);
    if s < SCORE_FLOOR { 0.0 } else { s }
}

/// Score `packed` (concatenated comparables) vs `anchor`.
fn score_packed(anchor: &PartView, views: &[PartView], packed: &[usize]) -> f64 {
    let mut concat = String::new();
    let mut total_len = 0usize;
    for &i in packed {
        concat.push_str(&views[i].comparable);
        total_len += views[i].comparable_len;
    }
    score(
        &anchor.comparable,
        anchor.comparable_len,
        &concat,
        total_len,
    )
}

/// Greedily grow `packed` (seeded with one view from the opposite
/// side) by inserting tag-compatible candidates from `options` at
/// the score-maximising position.
fn pack_short_parts(
    anchor: &PartView,
    packed_seed: usize,
    options: &[usize],
    views: &[PartView],
) -> Vec<usize> {
    let mut packed: Vec<usize> = vec![packed_seed];
    for &op in options {
        if packed.contains(&op) {
            continue;
        }
        if !anchor.tag.can_match(views[op].tag) {
            continue;
        }
        let packed_len: usize = packed.iter().map(|&i| views[i].comparable_len).sum();
        if packed_len >= anchor.form_len {
            break;
        }
        let mut best_score = score_packed(anchor, views, &packed);
        let mut best_packed: Option<Vec<usize>> = None;
        for i in 0..=packed.len() {
            let mut candidate = packed.clone();
            candidate.insert(i, op);
            let s = score_packed(anchor, views, &candidate);
            if s > best_score {
                best_score = s;
                best_packed = Some(candidate);
            }
        }
        if let Some(p) = best_packed {
            packed = p;
        }
    }
    packed
}

/// Rust-internal alignment core operating on view indices.
///
/// Returns `(left_order, right_order, matched)` where:
/// * `left_order`, `right_order` are the view indices in aligned
///   order followed by any unmatched tails (length-desc).
/// * `matched` is `true` iff the greedy loop consumed at least one
///   pair — distinguishes the "nothing aligned" fallback case.
fn align_views(
    left_views: &[PartView],
    right_views: &[PartView],
) -> (Vec<usize>, Vec<usize>, bool) {
    // Stable length-desc sort keeps the tie-break deterministic via
    // input order.
    let mut left_active: Vec<usize> = (0..left_views.len()).collect();
    left_active.sort_by(|a, b| left_views[*b].form_len.cmp(&left_views[*a].form_len));
    let mut right_active: Vec<usize> = (0..right_views.len()).collect();
    right_active.sort_by(|a, b| right_views[*b].form_len.cmp(&right_views[*a].form_len));

    let mut left_out: Vec<usize> = Vec::with_capacity(left_views.len());
    let mut right_out: Vec<usize> = Vec::with_capacity(right_views.len());
    let mut matched = false;

    loop {
        if left_active.is_empty() || right_active.is_empty() {
            break;
        }
        let mut best_score = 0.0_f64;
        let mut best_left: Vec<usize> = Vec::new();
        let mut best_right: Vec<usize> = Vec::new();

        // Left-major product walk for iteration-order determinism.
        'outer: for &li in &left_active {
            for &ri in &right_active {
                let lv = &left_views[li];
                let rv = &right_views[ri];
                if !lv.tag.can_match(rv.tag) {
                    continue;
                }
                if lv.comparable == rv.comparable {
                    best_score = 1.0;
                    best_left = vec![li];
                    best_right = vec![ri];
                    break 'outer;
                }
                let base = score(
                    &lv.comparable,
                    lv.comparable_len,
                    &rv.comparable,
                    rv.comparable_len,
                );
                if base <= best_score {
                    continue;
                }
                // Candidate pair beats current best. Try packing on
                // the side with the shorter form (if any) to pull in
                // extra parts that might align with the longer token.
                let (cl, cr) = if lv.form_len > rv.form_len {
                    let options: Vec<usize> = right_active
                        .iter()
                        .copied()
                        .filter(|&idx| idx != ri)
                        .collect();
                    (vec![li], pack_short_parts(lv, ri, &options, right_views))
                } else if rv.form_len > lv.form_len {
                    let options: Vec<usize> = left_active
                        .iter()
                        .copied()
                        .filter(|&idx| idx != li)
                        .collect();
                    (pack_short_parts(rv, li, &options, left_views), vec![ri])
                } else {
                    (vec![li], vec![ri])
                };
                let final_score = if cl.len() > 1 {
                    score_packed(rv, left_views, &cl)
                } else if cr.len() > 1 {
                    score_packed(lv, right_views, &cr)
                } else {
                    base
                };
                if final_score > best_score {
                    best_score = final_score;
                    best_left = cl;
                    best_right = cr;
                }
            }
        }

        if best_score == 0.0 {
            break;
        }

        matched = true;
        // Consume the chosen indices from both actives, preserving
        // the remaining order.
        left_active.retain(|i| !best_left.contains(i));
        right_active.retain(|i| !best_right.contains(i));
        left_out.extend(best_left);
        right_out.extend(best_right);
    }

    // Append remaining active indices as the unmatched tail
    // (length-desc, same order as during the loop).
    left_out.extend(left_active);
    right_out.extend(right_active);
    (left_out, right_out, matched)
}

/// Greedy-align two lists of name parts so comparable tokens share
/// the same output index.
///
/// Used by the name matcher to reorder remaining tokens after
/// symbolic tagging so a downstream per-index similarity pass
/// compares like with like. Pairs are chosen by a length-desc,
/// left-major walk over edit-similarity scores; ties are broken
/// stably by input order so the output is deterministic.
///
/// Returns `([], tag_sort(right))` when `left` is empty, falls back
/// to `(tag_sort(left), tag_sort(right))` when no pair scores above
/// the similarity floor, otherwise returns the greedy-aligned pair.
#[pyfunction]
#[pyo3(name = "align_person_name_order")]
pub fn py_align_person_name_order(
    py: Python<'_>,
    left: Vec<Py<NamePart>>,
    right: Vec<Py<NamePart>>,
) -> (Vec<Py<NamePart>>, Vec<Py<NamePart>>) {
    if left.is_empty() {
        return (left, tag_sort_parts(py, right));
    }

    let left_views = extract_views(py, &left);
    let right_views = extract_views(py, &right);
    let (left_order, right_order, matched) = align_views(&left_views, &right_views);

    if !matched {
        return (tag_sort_parts(py, left), tag_sort_parts(py, right));
    }

    let left_result: Vec<Py<NamePart>> = left_order
        .iter()
        .map(|&i| left[left_views[i].origin].clone_ref(py))
        .collect();
    let right_result: Vec<Py<NamePart>> = right_order
        .iter()
        .map(|&i| right[right_views[i].origin].clone_ref(py))
        .collect();
    (left_result, right_result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn view(origin: usize, form_len: usize, comparable: &str, tag: NamePartTag) -> PartView {
        PartView {
            origin,
            form_len,
            comparable: comparable.to_string(),
            comparable_len: comparable.chars().count(),
            tag,
        }
    }

    #[test]
    fn score_equal_strings_is_one() {
        assert_eq!(score("john", 4, "john", 4), 1.0);
    }

    #[test]
    fn score_below_floor_is_zero() {
        assert_eq!(score("john", 4, "xyz", 3), 0.0);
    }

    #[test]
    fn score_close_match_is_high() {
        let s = score("doe", 3, "dow", 3);
        assert!((s - 2.0 / 3.0).abs() < 1e-9, "got {s}");
    }

    #[test]
    fn pack_greedy_improves_anchor_match() {
        let anchor = view(0, 7, "alsabah", NamePartTag::UNSET);
        let views = vec![
            view(0, 2, "al", NamePartTag::UNSET),
            view(1, 5, "sabah", NamePartTag::UNSET),
        ];
        let packed = pack_short_parts(&anchor, 1, &[0], &views);
        assert_eq!(packed, vec![0, 1]);
    }

    #[test]
    fn pack_respects_tag_gate() {
        let anchor = view(0, 7, "alsabah", NamePartTag::FAMILY);
        let views = vec![
            view(0, 2, "al", NamePartTag::GIVEN),
            view(1, 5, "sabah", NamePartTag::FAMILY),
        ];
        let packed = pack_short_parts(&anchor, 1, &[0], &views);
        assert_eq!(packed, vec![1]);
    }

    #[test]
    fn align_reversed_order_pairs_up() {
        let lv = vec![
            view(0, 4, "john", NamePartTag::UNSET),
            view(1, 3, "doe", NamePartTag::UNSET),
        ];
        let rv = vec![
            view(0, 3, "doe", NamePartTag::UNSET),
            view(1, 4, "john", NamePartTag::UNSET),
        ];
        let (lout, rout, matched) = align_views(&lv, &rv);
        assert!(matched);
        assert_eq!(lv[lout[0]].comparable, rv[rout[0]].comparable);
        assert_eq!(lv[lout[1]].comparable, rv[rout[1]].comparable);
    }

    #[test]
    fn align_no_match_signals_fallback() {
        let lv = vec![view(0, 4, "john", NamePartTag::UNSET)];
        let rv = vec![view(0, 3, "xyz", NamePartTag::UNSET)];
        let (_lout, _rout, matched) = align_views(&lv, &rv);
        assert!(!matched);
    }
}
