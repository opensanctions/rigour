// String distance wrappers around the `rapidfuzz` Rust crate. We mirror the
// Python `rapidfuzz.distance` contract that callers rely on: when a
// `score_cutoff` is supplied and the true distance exceeds it, return
// `cutoff + 1` rather than the actual value. The Rust crate returns
// `Option<usize>` (None on exceed) — we translate that to the Python convention
// at this layer so existing rigour call sites (e.g. territories/lookup.py's
// initial `best_distance = cutoff + 1` then `distance < best_distance`) keep
// working unchanged.

use rapidfuzz::distance::{damerau_levenshtein, jaro_winkler, levenshtein};

pub fn levenshtein(left: &str, right: &str, score_cutoff: Option<usize>) -> usize {
    match score_cutoff {
        Some(cutoff) => {
            let args = levenshtein::Args::default().score_cutoff(cutoff);
            levenshtein::distance_with_args(left.chars(), right.chars(), &args)
                .unwrap_or(cutoff + 1)
        }
        None => levenshtein::distance(left.chars(), right.chars()),
    }
}

pub fn dam_levenshtein(left: &str, right: &str, score_cutoff: Option<usize>) -> usize {
    match score_cutoff {
        Some(cutoff) => {
            let args = damerau_levenshtein::Args::default().score_cutoff(cutoff);
            damerau_levenshtein::distance_with_args(left.chars(), right.chars(), &args)
                .unwrap_or(cutoff + 1)
        }
        None => damerau_levenshtein::distance(left.chars(), right.chars()),
    }
}

pub fn jaro_winkler_similarity(left: &str, right: &str) -> f64 {
    jaro_winkler::similarity(left.chars(), right.chars())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn levenshtein_basic() {
        assert_eq!(levenshtein("foo", "foo", None), 0);
        assert_eq!(levenshtein("foo", "bar", None), 3);
        assert_eq!(levenshtein("bar", "bra", None), 2);
        assert_eq!(levenshtein("foo", "foobar", None), 3);
        assert_eq!(levenshtein("foo", "Foo", None), 1);
    }

    #[test]
    fn levenshtein_cutoff_returns_cutoff_plus_one_when_exceeded() {
        // Python rapidfuzz convention: exceeded cutoff returns cutoff+1.
        assert_eq!(levenshtein("foo", "xxxxxxx", Some(2)), 3);
        assert_eq!(levenshtein("foo", "foo", Some(5)), 0);
    }

    #[test]
    fn damerau_levenshtein_basic() {
        assert_eq!(dam_levenshtein("foo", "foo", None), 0);
        assert_eq!(dam_levenshtein("foo", "bar", None), 3);
        assert_eq!(dam_levenshtein("bar", "bar", None), 0);
        // True (not OSA) Damerau-Levenshtein: "bar" → "bra" is a single
        // transposition, distance 1.
        assert_eq!(dam_levenshtein("bar", "bra", None), 1);
        assert_eq!(dam_levenshtein("foo", "foobar", None), 3);
        assert_eq!(dam_levenshtein("foo", "Foo", None), 1);
    }

    #[test]
    fn jaro_winkler_basic() {
        assert!((jaro_winkler_similarity("foo", "foo") - 1.0).abs() < 1e-9);
        let sim = jaro_winkler_similarity("foo", "foox");
        assert!(sim > 0.9 && sim < 1.0);
    }
}
