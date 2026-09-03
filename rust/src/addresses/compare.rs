// Address comparison scorer.
//
// Grown iteratively: every rule here has earned its place through a
// measured delta on the contrib/address_bench corpus. Current shape:
// greedy best-pair token alignment over analyzed tokens, scored by
// length-weighted edit-distance similarity.

use std::mem;
use std::sync::Arc;

#[cfg(feature = "python")]
use pyo3::prelude::*;

use crate::addresses::analyze::{Address, analyze_cached};
use crate::addresses::token::{AddressToken, TokenClass};
use crate::text::distance::levenshtein_cutoff;

/// Edit budget as a fraction of the shorter token's length (in
/// codepoints); token pairs beyond the budget don't align.
const MAX_EDITS_PCT: f64 = 0.30;

/// Similarity credited to two tokens equivalent through their class
/// payload without being literally equal — Keywords sharing a
/// canonical form (boulevard/blvd), Territories sharing a code
/// (syria/syrian arab republic): slightly weaker evidence than
/// identity.
const ALIAS_SIM: f64 = 0.90;

/// Score deduction per cross-pair of unmatched numbers: both sides
/// asserting a number the other lacks is stronger negative signal
/// than the plain residue weight of two short tokens.
const NUMBER_MISMATCH_PENALTY: f64 = 0.7;

/// One accepted token alignment: query index, result index,
/// similarity.
type Bound = (usize, usize, f64);

/// The best pair out of a list×list address comparison, with the
/// evidence that produced it.
#[cfg_attr(
    feature = "python",
    pyclass(frozen, get_all, skip_from_py_object, module = "rigour._core")
)]
#[derive(Debug, Clone, PartialEq)]
pub struct AddressMatch {
    /// Similarity of the winning pair in [0.0, 1.0].
    pub score: f64,
    /// Query-side address of the winning pair, as supplied.
    pub query: String,
    /// Result-side address of the winning pair, as supplied.
    pub result: String,
    /// One-line alignment summary over comparable token forms:
    /// aligned tokens in query order (`berlin` when identical,
    /// `boulevard~blvd` when aligned by edit distance or class
    /// equivalence), then `-tok` for query-only and `+tok` for
    /// result-only tokens.
    pub detail: String,
}

#[cfg(feature = "python")]
#[pymethods]
impl AddressMatch {
    fn __repr__(&self) -> String {
        format!(
            "AddressMatch(score={:.3}, query={:?}, result={:?}, detail={:?})",
            self.score, self.query, self.result, self.detail
        )
    }
}

/// Compare two address strings, returning a similarity in [0.0, 1.0].
pub fn compare(query: &str, result: &str) -> f64 {
    compare_many(&[query], &[result])
}

/// Compare every query address against every result address and
/// return the highest pairwise score. Each string is analyzed once
/// (through the LRU), so the list×list loop costs analysis per
/// distinct string plus one alignment per pair.
pub fn compare_many<S: AsRef<str>>(queries: &[S], results: &[S]) -> f64 {
    let qry = analyze_all(queries);
    let res = analyze_all(results);
    best_pair(&qry, &res).map_or(0.0, |b| b.score)
}

/// Compare every query address against every result address and
/// return the best pair with its alignment detail, or `None` when
/// either side holds nothing analyzable.
pub fn match_many<S: AsRef<str>>(queries: &[S], results: &[S]) -> Option<AddressMatch> {
    let qry = analyze_all(queries);
    let res = analyze_all(results);
    let best = best_pair(&qry, &res)?;
    let (query, qaddr) = &qry[best.qi];
    let (result, raddr) = &res[best.ri];
    Some(AddressMatch {
        score: best.score,
        query: query.to_string(),
        result: result.to_string(),
        detail: describe(&qaddr.tokens, &raddr.tokens, &best.bound),
    })
}

/// Winning pair of a list×list comparison.
struct Best {
    score: f64,
    qi: usize,
    ri: usize,
    bound: Vec<Bound>,
}

fn analyze_all<S: AsRef<str>>(texts: &[S]) -> Vec<(&str, Arc<Address>)> {
    texts
        .iter()
        .map(AsRef::as_ref)
        .filter_map(|s| analyze_cached(s).map(|a| (s, a)))
        .collect()
}

/// Score every pair and keep the best. The alignment writes its
/// bound pairs into one scratch buffer that is swapped into the
/// winner's slot on improvement, so the loop allocates nothing per
/// pair beyond the alignment's own candidate list.
fn best_pair(qry: &[(&str, Arc<Address>)], res: &[(&str, Arc<Address>)]) -> Option<Best> {
    let mut best: Option<Best> = None;
    let mut scratch: Vec<Bound> = Vec::new();
    for (qi, (_, q)) in qry.iter().enumerate() {
        for (ri, (_, r)) in res.iter().enumerate() {
            let score = align_tokens(&q.tokens, &r.tokens, &mut scratch);
            let improved = best.as_ref().is_none_or(|b| score > b.score);
            if !improved {
                continue;
            }
            match best.as_mut() {
                Some(b) => {
                    b.score = score;
                    b.qi = qi;
                    b.ri = ri;
                    mem::swap(&mut b.bound, &mut scratch);
                }
                None => {
                    best = Some(Best {
                        score,
                        qi,
                        ri,
                        bound: mem::take(&mut scratch),
                    });
                }
            }
            if score >= 1.0 {
                return best;
            }
        }
    }
    best
}

/// Render the alignment as one line: aligned tokens in query order
/// (`tok` when both comparable forms agree, `q~r` otherwise), then
/// `-tok` for unmatched query tokens and `+tok` for unmatched result
/// tokens.
fn describe(qry: &[AddressToken], res: &[AddressToken], bound: &[Bound]) -> String {
    let mut ordered: Vec<&Bound> = bound.iter().collect();
    ordered.sort_by_key(|b| b.0);
    let mut qry_used = vec![false; qry.len()];
    let mut res_used = vec![false; res.len()];
    let mut parts: Vec<String> = Vec::with_capacity(qry.len() + res.len());
    for &&(qi, ri, _) in &ordered {
        qry_used[qi] = true;
        res_used[ri] = true;
        let q = qry[qi].comparable();
        let r = res[ri].comparable();
        if q == r {
            parts.push(q.to_string());
        } else {
            parts.push(format!("{q}~{r}"));
        }
    }
    for (tok, used) in qry.iter().zip(&qry_used) {
        if !used {
            parts.push(format!("-{}", tok.comparable()));
        }
    }
    for (tok, used) in res.iter().zip(&res_used) {
        if !used {
            parts.push(format!("+{}", tok.comparable()));
        }
    }
    parts.join(" ")
}

/// Similarity of two tokens in [0.0, 1.0]. Two Number tokens match
/// exactly or not at all — compared on their canonical digit
/// strings (leading-zero-faithful, script-independent), with no
/// fuzzy credit between differing numbers. Everything else is fuzzy.
fn pair_similarity(a: &AddressToken, b: &AddressToken) -> f64 {
    match (&a.class, &b.class) {
        (TokenClass::Number { digits: da }, TokenClass::Number { digits: db }) => {
            if da == db {
                1.0
            } else {
                0.0
            }
        }
        (TokenClass::Keyword { canonical: ca }, TokenClass::Keyword { canonical: cb })
            if ca == cb =>
        {
            if a.comparable() == b.comparable() {
                1.0
            } else {
                ALIAS_SIM
            }
        }
        (TokenClass::Territory { codes: ca }, TokenClass::Territory { codes: cb })
            if ca.iter().any(|c| cb.contains(c)) =>
        {
            if a.comparable() == b.comparable() {
                1.0
            } else {
                ALIAS_SIM
            }
        }
        _ => token_similarity(a.comparable(), b.comparable()),
    }
}

/// Similarity of two token forms in [0.0, 1.0]: 1.0 for identical,
/// 0.0 when the edit distance exceeds the relative budget.
fn token_similarity(a: &str, b: &str) -> f64 {
    let a_len = a.chars().count();
    let b_len = b.chars().count();
    if a_len == 0 || b_len == 0 {
        return 0.0;
    }
    let cutoff = (a_len.min(b_len) as f64 * MAX_EDITS_PCT).ceil() as usize;
    let distance = levenshtein_cutoff(a, b, cutoff);
    if distance > cutoff {
        return 0.0;
    }
    1.0 - (distance as f64 / a_len.max(b_len) as f64)
}

/// Greedy best-pair alignment: the highest-similarity pair binds
/// first, each token aligns at most once. The score is the
/// similarity-discounted matched weight over the total weight of
/// both sides, with token weight proportional to length. The
/// accepted pairs are written to `bound` (cleared first).
fn align_tokens(qry: &[AddressToken], res: &[AddressToken], bound: &mut Vec<Bound>) -> f64 {
    bound.clear();
    let total: usize = qry
        .iter()
        .chain(res.iter())
        .map(|t| t.comparable().chars().count())
        .sum();
    if total == 0 {
        return 0.0;
    }

    let mut pairs: Vec<(f64, usize, usize)> = Vec::new();
    for (qi, qt) in qry.iter().enumerate() {
        for (ri, rt) in res.iter().enumerate() {
            let sim = pair_similarity(qt, rt);
            if sim > 0.0 {
                pairs.push((sim, qi, ri));
            }
        }
    }
    pairs.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)).then(a.2.cmp(&b.2)));

    let mut qry_used = vec![false; qry.len()];
    let mut res_used = vec![false; res.len()];
    let mut matched = 0.0;
    for (sim, qi, ri) in pairs {
        if qry_used[qi] || res_used[ri] {
            continue;
        }
        qry_used[qi] = true;
        res_used[ri] = true;
        bound.push((qi, ri, sim));
        let weight = qry[qi].comparable().chars().count() + res[ri].comparable().chars().count();
        matched += sim * weight as f64;
    }

    let penalty = NUMBER_MISMATCH_PENALTY * unmatched_pairs(qry, &qry_used, res, &res_used);
    (matched / total as f64 - penalty).max(0.0)
}

/// Number of cross-pairs of unmatched Number tokens — the smaller
/// side's count, so one-sided extras (subset relations) don't count.
fn unmatched_pairs(
    qry: &[AddressToken],
    qry_used: &[bool],
    res: &[AddressToken],
    res_used: &[bool],
) -> f64 {
    let count = |toks: &[AddressToken], used: &[bool]| {
        toks.iter()
            .zip(used)
            .filter(|(t, u)| !**u && matches!(t.class, TokenClass::Number { .. }))
            .count()
    };
    count(qry, qry_used).min(count(res, res_used)) as f64
}

#[cfg(test)]
mod tests {
    use super::*;

    fn detail(query: &str, result: &str) -> String {
        match_many(&[query], &[result]).unwrap().detail
    }

    #[test]
    fn identical_scores_one() {
        assert_eq!(
            compare("Bahnhofstr. 12, Berlin", "Bahnhofstr. 12, Berlin"),
            1.0
        );
    }

    #[test]
    fn case_and_punctuation_invariant() {
        assert_eq!(
            compare("BAHNHOFSTR 12 BERLIN", "bahnhofstr. 12, berlin"),
            1.0
        );
    }

    #[test]
    fn reordered_fields_score_one() {
        assert_eq!(
            compare(
                "Bahnhofstr. 12, 10115 Berlin",
                "10115 Berlin, Bahnhofstr. 12"
            ),
            1.0
        );
    }

    #[test]
    fn narrow_transliteration_aligns() {
        let score = compare("Тверская 4, Москва", "Tverskaya 4, Moskva");
        assert!(score > 0.8, "got {score}");
    }

    #[test]
    fn small_typo_scores_high_but_below_one() {
        let score = compare("Bahnhofstrasse 12, Berlin", "Bahnhofstrase 12, Berlin");
        assert!(score > 0.9 && score < 1.0, "got {score}");
    }

    #[test]
    fn dissimilar_scores_low() {
        let score = compare("Bahnhofstr. 12, Berlin", "Calle Mayor 3, Madrid");
        assert!(score < 0.2, "got {score}");
    }

    #[test]
    fn differing_numbers_earn_no_fuzzy_credit() {
        let close = compare("Bahnhofstr. 12, Berlin", "Bahnhofstr. 14, Berlin");
        let same = compare("Bahnhofstr. 12, Berlin", "Bahnhofstr. 12, Berlin");
        assert!(same == 1.0 && close < 0.95, "close={close}");
    }

    #[test]
    fn number_mismatch_penalized_but_one_sided_extra_is_not() {
        // Both sides asserting a number the other lacks: penalty.
        let mismatch = compare("Hauptstr. 5, 10115 Berlin", "Hauptstr. 7, 10115 Berlin");
        // One side simply lacking the number: plain residue, no penalty.
        let subset = compare("Hauptstr. 5, 10115 Berlin", "Hauptstr., 10115 Berlin");
        assert!(mismatch < 0.5, "mismatch={mismatch}");
        assert!(
            subset > mismatch + 0.3,
            "subset={subset} mismatch={mismatch}"
        );
    }

    #[test]
    fn keyword_matches_across_alias_forms() {
        // "boulevard" vs "blvd" is far beyond the edit budget; the
        // shared canonical form aligns them — slightly below the
        // literal-identity score.
        let score = compare(
            "Sunset Boulevard 12, Los Angeles",
            "Sunset Blvd 12, Los Angeles",
        );
        assert!(score > 0.95 && score < 1.0, "got {score}");
    }

    #[test]
    fn territories_match_on_shared_code() {
        // "syria" and "syrian arab republic" share no edit-distance
        // proximity; the shared territory code aligns them.
        let score = compare(
            "PO Box 7155, Damascus, Syria",
            "PO Box 7155, Damascus, Syrian Arab Republic",
        );
        assert!(score > 0.9, "got {score}");
    }

    #[test]
    fn glued_house_numbers_align() {
        // "Д.17" used to stay one Text token, turning the shared
        // house number into a penalized mismatch.
        let score = compare("Тверская Д.17, Москва", "Tverskaya 17, Moskva");
        assert!(score > 0.7, "got {score}");
    }

    #[test]
    fn ordinal_aligns_with_plain_number() {
        let score = compare("30th Ave, Fargo", "30 Ave, Fargo");
        assert!(score > 0.9, "got {score}");
    }

    #[test]
    fn digit_scripts_fold_for_number_match() {
        let score = compare("شارع الملك فهد ١٧", "شارع الملك فهد 17");
        assert_eq!(score, 1.0);
    }

    #[test]
    fn compare_many_returns_best_pair() {
        let queries = vec![
            "Calle Mayor 3, Madrid".to_string(),
            "Bahnhofstr. 12, Berlin".to_string(),
        ];
        let results = vec![
            "10115 Berlin, Bahnhofstrasse 12".to_string(),
            "Bahnhofstr. 12, Berlin".to_string(),
        ];
        assert_eq!(compare_many(&queries, &results), 1.0);
        assert_eq!(compare_many(&queries, &[]), 0.0);
        assert_eq!(compare_many(&[], &results), 0.0);
        assert_eq!(compare_many(&["...".to_string()], &results), 0.0);
    }

    #[test]
    fn empty_input_scores_zero() {
        assert_eq!(compare("", "Bahnhofstr. 12"), 0.0);
        assert_eq!(compare("...", "Bahnhofstr. 12"), 0.0);
        assert_eq!(compare("", ""), 0.0);
    }

    #[test]
    fn match_many_returns_winning_raw_pair() {
        let queries = ["Calle Mayor 3, Madrid", "Bahnhofstr. 12, Berlin"];
        let results = ["10115 Berlin, Bahnhofstrasse 12", "Bahnhofstr. 12, Berlin"];
        let m = match_many(&queries, &results).unwrap();
        assert_eq!(m.score, 1.0);
        assert_eq!(m.query, "Bahnhofstr. 12, Berlin");
        assert_eq!(m.result, "Bahnhofstr. 12, Berlin");
        assert_eq!(m.detail, "bahnhofstr 12 berlin");
        assert_eq!(m.score, compare_many(&queries, &results));
    }

    #[test]
    fn match_many_none_without_analyzable_side() {
        assert!(match_many(&["Bahnhofstr. 12"], &[]).is_none());
        assert!(match_many::<&str>(&[], &[]).is_none());
        assert!(match_many(&["..."], &["Bahnhofstr. 12"]).is_none());
    }

    #[test]
    fn match_many_zero_score_still_reports_pair() {
        let m = match_many(&["Bahnhofstr. 12, Berlin"], &["Calle Mayor 3, Madrid"]).unwrap();
        assert!(m.score < 0.2, "got {}", m.score);
        assert!(m.detail.starts_with('-'), "got {}", m.detail);
        assert!(m.detail.contains("+calle"), "got {}", m.detail);
    }

    #[test]
    fn detail_marks_alias_and_residue() {
        assert_eq!(
            detail("Sunset Boulevard 12, Los Angeles", "Sunset Blvd 12, LA"),
            "sunset boulevard~blvd 12 -los -angeles +la"
        );
    }

    #[test]
    fn detail_marks_fuzzy_pair() {
        assert_eq!(
            detail("Bahnhofstrasse 12, Berlin", "Bahnhofstrase 12, Berlin"),
            "bahnhofstrasse~bahnhofstrase 12 berlin"
        );
    }

    #[test]
    fn detail_shows_number_conflict_as_residue() {
        assert_eq!(
            detail("Hauptstr. 5, 10115 Berlin", "Hauptstr. 7, 10115 Berlin"),
            "hauptstr 10115 berlin -5 +7"
        );
    }

    #[test]
    fn detail_orders_aligned_by_query() {
        assert_eq!(
            detail(
                "Bahnhofstr. 12, 10115 Berlin",
                "10115 Berlin, Bahnhofstr. 12"
            ),
            "bahnhofstr 12 10115 berlin"
        );
    }
}
