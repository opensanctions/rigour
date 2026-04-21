//! String edit-distance primitives for internal Rust consumers.
//!
//! Exposes plain Levenshtein and Damerau-Levenshtein, each with an
//! optional early-exit cutoff variant. Not wired through PyO3 —
//! Python callers use the `rapidfuzz` package directly (which also
//! provides the opcodes / alignment API the Rust `rapidfuzz` crate
//! doesn't).
//!
//! Backed by the `rapidfuzz` crate's bit-parallel implementations
//! (Myers/Hyyrö for short strings, block-wise with Ukkonen band
//! for longer inputs). All functions operate on Unicode code
//! points, so `"café"` vs `"cafe"` is 1 edit (not the UTF-8
//! byte-delta).

use rapidfuzz::distance::{damerau_levenshtein, levenshtein};

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
}
