// Address comparison scorer.
//
// Grown iteratively: every rule here has earned its place through a
// measured delta on the contrib/address_bench corpus. Current shape:
// greedy best-pair token alignment over analyzed tokens, scored by
// length-weighted edit-distance similarity.

use crate::addresses::analyze::analyze;
use crate::addresses::token::{AddressToken, TokenClass};
use crate::text::distance::levenshtein_cutoff;
use crate::text::numbers::fold_digits;

/// Edit budget as a fraction of the shorter token's length (in
/// codepoints); token pairs beyond the budget don't align.
const MAX_EDITS_PCT: f64 = 0.2;

/// Compare two address strings, returning a similarity in [0.0, 1.0].
pub fn compare(query: &str, result: &str) -> f64 {
    let Some(qry) = analyze(query) else {
        return 0.0;
    };
    let Some(res) = analyze(result) else {
        return 0.0;
    };
    align_tokens(&qry.tokens, &res.tokens)
}

/// Similarity of two tokens in [0.0, 1.0]. Two Number tokens match
/// exactly or not at all — compared on their digit-folded surface
/// (leading-zero-faithful, script-independent), with no fuzzy
/// credit between differing numbers. Everything else is fuzzy.
fn pair_similarity(a: &AddressToken, b: &AddressToken) -> f64 {
    match (&a.class, &b.class) {
        (TokenClass::Number { .. }, TokenClass::Number { .. }) => {
            if fold_digits(a.comparable()) == fold_digits(b.comparable()) {
                1.0
            } else {
                0.0
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
    matched / total as f64
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
    fn digit_scripts_fold_for_number_match() {
        let score = compare("شارع الملك فهد ١٧", "شارع الملك فهد 17");
        assert_eq!(score, 1.0);
    }

    #[test]
    fn empty_input_scores_zero() {
        assert_eq!(compare("", "Bahnhofstr. 12"), 0.0);
        assert_eq!(compare("...", "Bahnhofstr. 12"), 0.0);
        assert_eq!(compare("", ""), 0.0);
    }
}
