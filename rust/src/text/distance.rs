//! String edit-distance and similarity primitives.
//!
//! Exposes plain Levenshtein and Damerau-Levenshtein (each with an
//! optional early-exit cutoff variant) and Jaro-Winkler similarity.
//! These back the `raw_*` PyO3 bindings consumed by
//! `rigour.text.distance`, plus the in-Rust callers in
//! `names::pick` / `names::ordering`.
//!
//! Backed by the `rapidfuzz` crate's bit-parallel implementations
//! (Myers/Hyyrö for short strings, block-wise with Ukkonen band
//! for longer inputs). All functions operate on Unicode code
//! points, so `"café"` vs `"cafe"` is 1 edit (not the UTF-8
//! byte-delta).

use rapidfuzz::distance::{damerau_levenshtein, jaro, jaro_winkler, levenshtein};

/// Unbounded Levenshtein distance: insertions, deletions, and
/// substitutions each cost 1. Transpositions cost 2 (one insert +
/// one delete) — use [`damerau_levenshtein`] if transpositions
/// should count as 1.
pub fn levenshtein(a: &str, b: &str) -> usize {
    levenshtein::distance(a.chars(), b.chars())
}

/// Levenshtein distance with an early-exit cutoff. Returns
/// `cutoff + 1` when the true distance exceeds `cutoff`, matching
/// the `score_cutoff` convention of Python rapidfuzz. Callers
/// migrating from `Levenshtein.distance(a, b, score_cutoff=N)` get
/// the same semantics.
pub fn levenshtein_cutoff(a: &str, b: &str, cutoff: usize) -> usize {
    let args = levenshtein::Args::default().score_cutoff(cutoff);
    levenshtein::distance_with_args(a.chars(), b.chars(), &args).unwrap_or(cutoff + 1)
}

/// Unbounded Damerau-Levenshtein distance: like
/// [`levenshtein`] but transposing two adjacent characters
/// counts as 1 edit instead of 2. Use when near-duplicate typos
/// with swapped letters ("Barak Obama" vs "Barack Obama") should
/// score as closer matches than plain Levenshtein reports.
pub fn damerau_levenshtein(a: &str, b: &str) -> usize {
    damerau_levenshtein::distance(a.chars(), b.chars())
}

/// Damerau-Levenshtein distance with an early-exit cutoff — same
/// `score_cutoff` semantics as [`levenshtein_cutoff`].
pub fn damerau_levenshtein_cutoff(a: &str, b: &str, cutoff: usize) -> usize {
    let args = damerau_levenshtein::Args::default().score_cutoff(cutoff);
    damerau_levenshtein::distance_with_args(a.chars(), b.chars(), &args).unwrap_or(cutoff + 1)
}

/// Jaro similarity in `[0.0, 1.0]`: 1.0 means identical, 0.0 means
/// no shared characters within the matching window. Use this when
/// shared prefixes shouldn't be weighted any more heavily than
/// shared characters elsewhere — e.g. matching against names where
/// a common prefix is just a frequent term ("Saint", "Banco")
/// rather than evidence of identity. Otherwise prefer
/// [`jaro_winkler_similarity`].
pub fn jaro_similarity(a: &str, b: &str) -> f64 {
    jaro::normalized_similarity(a.chars(), b.chars())
}

/// Jaro-Winkler similarity in `[0.0, 1.0]`: 1.0 means identical,
/// 0.0 means no shared characters within the matching window.
/// Includes the standard 0.1 prefix bonus weighting up to 4 leading
/// characters, which makes it the default choice for matching short
/// names where shared prefixes are strong evidence ("Vladimir" vs
/// "Vladmir" scores higher than plain Jaro would give).
pub fn jaro_winkler_similarity(a: &str, b: &str) -> f64 {
    jaro_winkler::normalized_similarity(a.chars(), b.chars())
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- levenshtein ---

    #[test]
    fn levenshtein_ascii_basic() {
        assert_eq!(levenshtein("foo", "foo"), 0);
        assert_eq!(levenshtein("foo", "bar"), 3);
        // "bar" vs "bra" is a transposition — 2 edits under plain
        // Levenshtein, 1 under Damerau (see test below).
        assert_eq!(levenshtein("bar", "bra"), 2);
        assert_eq!(levenshtein("foo", "foobar"), 3);
        assert_eq!(levenshtein("foo", "Foo"), 1);
    }

    #[test]
    fn levenshtein_unicode_operates_on_codepoints() {
        assert_eq!(levenshtein("café", "cafe"), 1);
        assert_eq!(levenshtein("naïve", "naive"), 1);
        assert_eq!(levenshtein("Straße", "Strasse"), 2);
    }

    #[test]
    fn levenshtein_cyrillic() {
        assert_eq!(levenshtein("Путин", "Путин"), 0);
        assert_eq!(levenshtein("Путин", "Путен"), 1);
    }

    #[test]
    fn levenshtein_empty() {
        assert_eq!(levenshtein("", ""), 0);
        assert_eq!(levenshtein("abc", ""), 3);
        assert_eq!(levenshtein("", "abc"), 3);
    }

    #[test]
    fn levenshtein_cutoff_returns_actual_when_under() {
        assert_eq!(levenshtein_cutoff("foo", "foo", 5), 0);
        assert_eq!(levenshtein_cutoff("foo", "bar", 5), 3);
        assert_eq!(levenshtein_cutoff("foo", "bar", 3), 3);
    }

    #[test]
    fn levenshtein_cutoff_returns_cutoff_plus_one_when_over() {
        assert_eq!(levenshtein_cutoff("foo", "xxxxxxx", 2), 3);
        assert_eq!(levenshtein_cutoff("hello", "xxxxx", 1), 2);
    }

    // --- damerau_levenshtein ---

    #[test]
    fn damerau_counts_transposition_as_one() {
        // The distinguishing case: adjacent-char swap is 1 edit
        // under Damerau, 2 under plain Levenshtein.
        assert_eq!(damerau_levenshtein("bar", "bra"), 1);
        assert_eq!(damerau_levenshtein("abcd", "abdc"), 1);
        // Non-adjacent swaps still cost 2.
        assert_eq!(damerau_levenshtein("abcd", "dbca"), 2);
    }

    #[test]
    fn damerau_agrees_with_levenshtein_on_non_transpositions() {
        assert_eq!(damerau_levenshtein("foo", "foo"), 0);
        assert_eq!(damerau_levenshtein("foo", "bar"), 3);
        assert_eq!(damerau_levenshtein("café", "cafe"), 1);
        assert_eq!(damerau_levenshtein("Путин", "Путен"), 1);
    }

    #[test]
    fn damerau_empty() {
        assert_eq!(damerau_levenshtein("", ""), 0);
        assert_eq!(damerau_levenshtein("abc", ""), 3);
    }

    #[test]
    fn damerau_cutoff_behaves_like_levenshtein_cutoff() {
        assert_eq!(damerau_levenshtein_cutoff("foo", "foo", 5), 0);
        assert_eq!(damerau_levenshtein_cutoff("bar", "bra", 2), 1);
        // True distance > cutoff → cutoff + 1.
        assert_eq!(damerau_levenshtein_cutoff("foo", "xxxxxxx", 2), 3);
    }

    // --- jaro_similarity ---

    #[test]
    fn jaro_identity_and_disjoint() {
        assert_eq!(jaro_similarity("foo", "foo"), 1.0);
        assert_eq!(jaro_similarity("abc", "xyz"), 0.0);
    }

    #[test]
    fn jaro_no_prefix_bonus() {
        // The distinguishing case: plain Jaro doesn't reward shared
        // leading prefixes, so Jaro-Winkler always scores >= Jaro
        // for inputs that share a prefix.
        let j = jaro_similarity("Vladimir", "Vladmir");
        let jw = jaro_winkler_similarity("Vladimir", "Vladmir");
        assert!(jw > j, "jw={jw} j={j}");
    }

    #[test]
    fn jaro_empty_inputs() {
        assert_eq!(jaro_similarity("", ""), 1.0);
        assert_eq!(jaro_similarity("abc", ""), 0.0);
        assert_eq!(jaro_similarity("", "abc"), 0.0);
    }

    // --- jaro_winkler_similarity ---

    #[test]
    fn jaro_winkler_identity_and_disjoint() {
        assert_eq!(jaro_winkler_similarity("foo", "foo"), 1.0);
        // No shared codepoints within the matching window.
        assert_eq!(jaro_winkler_similarity("abc", "xyz"), 0.0);
    }

    #[test]
    fn jaro_winkler_prefix_bonus_lifts_near_misses() {
        // Shared 4-char prefix triggers the Winkler weighting; near-miss
        // scores noticeably above 0.9.
        assert!(jaro_winkler_similarity("Vladimir", "Vladmir") > 0.9);
        assert!(jaro_winkler_similarity("foo", "foox") > 0.9);
        assert!(jaro_winkler_similarity("foo", "foox") < 1.0);
    }

    #[test]
    fn jaro_winkler_unicode_codepoint_correct() {
        assert_eq!(jaro_winkler_similarity("café", "café"), 1.0);
        // One-codepoint diff in a 4-char string: comparison happens
        // at the codepoint level (é ≠ e), and the 3 shared leading
        // chars trigger the Winkler prefix bonus — score lands in
        // the high-Jaro band but well below 1.0.
        let s = jaro_winkler_similarity("café", "cafe");
        assert!(s > 0.8 && s < 1.0, "got {s}");
    }

    #[test]
    fn jaro_winkler_empty_inputs() {
        // Two empty strings are conventionally identical (1.0) under
        // the rapidfuzz crate's normalized_similarity.
        assert_eq!(jaro_winkler_similarity("", ""), 1.0);
        assert_eq!(jaro_winkler_similarity("abc", ""), 0.0);
        assert_eq!(jaro_winkler_similarity("", "abc"), 0.0);
    }
}
