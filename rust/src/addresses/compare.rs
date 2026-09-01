// Address comparison scorer.
//
// Deliberately minimal baseline: whole-string edit-distance
// similarity over address-normalized text. Every additional rule
// must earn its place through a measured delta on the
// contrib/address_bench corpus before it lands here.

use crate::text::distance::levenshtein_cutoff;
use crate::text::normalize::{Cleanup, Normalize, normalize};

/// Normalization applied to both sides before scoring.
const COMPARE_FLAGS: Normalize = Normalize::CASEFOLD.union(Normalize::ADDRESS);

/// Edit budget as a fraction of the shorter side's length (in
/// codepoints); pairs beyond the budget score 0.0.
const MAX_EDITS_PCT: f64 = 0.2;

/// Compare two address strings, returning a similarity in [0.0, 1.0].
pub fn compare(query: &str, result: &str) -> f64 {
    let Some(qry) = normalize(query, COMPARE_FLAGS, Cleanup::Noop) else {
        return 0.0;
    };
    let Some(res) = normalize(result, COMPARE_FLAGS, Cleanup::Noop) else {
        return 0.0;
    };
    let qry_len = qry.chars().count();
    let res_len = res.chars().count();
    if qry_len == 0 || res_len == 0 {
        return 0.0;
    }
    let cutoff = (qry_len.min(res_len) as f64 * MAX_EDITS_PCT).ceil() as usize;
    let distance = levenshtein_cutoff(&qry, &res, cutoff);
    if distance > cutoff {
        return 0.0;
    }
    1.0 - (distance as f64 / qry_len.max(res_len) as f64)
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
    fn small_typo_scores_high_but_below_one() {
        let score = compare("Bahnhofstrasse 12, Berlin", "Bahnhofstrase 12, Berlin");
        assert!(score > 0.9 && score < 1.0, "got {score}");
    }

    #[test]
    fn dissimilar_scores_zero() {
        assert_eq!(
            compare("Bahnhofstr. 12, Berlin", "Calle Mayor 3, Madrid"),
            0.0
        );
    }

    #[test]
    fn empty_input_scores_zero() {
        assert_eq!(compare("", "Bahnhofstr. 12"), 0.0);
        assert_eq!(compare("...", "Bahnhofstr. 12"), 0.0);
        assert_eq!(compare("", ""), 0.0);
    }
}
