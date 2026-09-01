// Address comparison scorer.
//
// Grown iteratively: every rule here has earned its place through a
// measured delta on the contrib/address_bench corpus. Current shape:
// greedy best-pair token alignment over analyzed tokens, scored by
// length-weighted edit-distance similarity.

use crate::addresses::analyze::analyze_cached;
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

/// Compare two address strings, returning a similarity in [0.0, 1.0].
pub fn compare(query: &str, result: &str) -> f64 {
    let Some(qry) = analyze_cached(query) else {
        return 0.0;
    };
    let Some(res) = analyze_cached(result) else {
        return 0.0;
    };
    align_tokens(&qry.tokens, &res.tokens)
}

/// Compare every query address against every result address and
/// return the highest pairwise score. Each string is analyzed once
/// (through the LRU), so the list×list loop costs analysis per
/// distinct string plus one alignment per pair.
pub fn compare_many(queries: &[String], results: &[String]) -> f64 {
    let qry: Vec<_> = queries.iter().filter_map(|s| analyze_cached(s)).collect();
    let res: Vec<_> = results.iter().filter_map(|s| analyze_cached(s)).collect();
    let mut best: f64 = 0.0;
    for q in &qry {
        for r in &res {
            let score = align_tokens(&q.tokens, &r.tokens);
            if score > best {
                best = score;
                if best >= 1.0 {
                    return best;
                }
            }
        }
    }
    best
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
/// both sides, with token weight proportional to length.
fn align_tokens(qry: &[AddressToken], res: &[AddressToken]) -> f64 {
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
}
