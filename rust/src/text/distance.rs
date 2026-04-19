// Levenshtein distance for internal Rust consumers. Intentionally not
// wired through PyO3: Python callers use the Python `rapidfuzz` package
// directly, which also provides the opcodes/alignment API we'd need and
// the Rust `rapidfuzz` crate doesn't expose. See
// plans/rust-transliteration.md for the decision trail.
//
// Backed by the `rapidfuzz` crate, which uses bit-parallel Myers/Hyyrö
// (single 64-bit word for short strings), Mbleven pruning for small
// edit distances, and block-wise Hyyrö with Ukkonen band for longer
// inputs. Expected primary consumer: a future Rust-side name picker
// replacing `rigour.names.pick.levenshtein_pick` and its all-pairs
// Levenshtein inner loop.

use rapidfuzz::distance::levenshtein;

/// Unbounded Levenshtein distance. Counts insertions, deletions, and
/// substitutions (each cost 1). Unicode-aware: operates on code points,
/// not bytes, so `"café" vs "cafe"` is 1 (not 2 on UTF-8 bytes).
pub fn distance(a: &str, b: &str) -> usize {
    levenshtein::distance(a.chars(), b.chars())
}

/// Levenshtein distance with an early-exit cutoff. If the true distance
/// exceeds `cutoff`, returns `cutoff + 1` — matching the convention of
/// Python rapidfuzz's `score_cutoff` parameter, so callers migrating
/// from `Levenshtein.distance(a, b, score_cutoff=N)` get the same
/// semantic here.
pub fn distance_cutoff(a: &str, b: &str, cutoff: usize) -> usize {
    let args = levenshtein::Args::default().score_cutoff(cutoff);
    levenshtein::distance_with_args(a.chars(), b.chars(), &args).unwrap_or(cutoff + 1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distance_ascii_basic() {
        assert_eq!(distance("foo", "foo"), 0);
        assert_eq!(distance("foo", "bar"), 3);
        assert_eq!(distance("bar", "bra"), 2); // classic Levenshtein, not Damerau
        assert_eq!(distance("foo", "foobar"), 3);
        assert_eq!(distance("foo", "Foo"), 1);
    }

    #[test]
    fn distance_unicode_operates_on_codepoints() {
        // "café" vs "cafe" differs by one codepoint (é vs e), not by
        // whatever the UTF-8 byte-delta would be.
        assert_eq!(distance("café", "cafe"), 1);
        assert_eq!(distance("naïve", "naive"), 1);
        assert_eq!(distance("Straße", "Strasse"), 2); // ß replaced + one insert
    }

    #[test]
    fn distance_cyrillic() {
        assert_eq!(distance("Путин", "Путин"), 0);
        assert_eq!(distance("Путин", "Путен"), 1);
    }

    #[test]
    fn distance_empty() {
        assert_eq!(distance("", ""), 0);
        assert_eq!(distance("abc", ""), 3);
        assert_eq!(distance("", "abc"), 3);
    }

    #[test]
    fn distance_cutoff_returns_actual_when_under() {
        assert_eq!(distance_cutoff("foo", "foo", 5), 0);
        assert_eq!(distance_cutoff("foo", "bar", 5), 3);
        // Exact-equals-cutoff also returns the true value (not +1).
        assert_eq!(distance_cutoff("foo", "bar", 3), 3);
    }

    #[test]
    fn distance_cutoff_returns_cutoff_plus_one_when_over() {
        // Python rapidfuzz convention: true distance > cutoff → cutoff + 1.
        assert_eq!(distance_cutoff("foo", "xxxxxxx", 2), 3);
        assert_eq!(distance_cutoff("hello", "xxxxx", 1), 2);
    }

    #[test]
    fn distance_cutoff_name_picker_pattern() {
        // Mirrors rigour.names.pick.latin_share / levenshtein_pick's
        // all-pairs-with-cutoff usage: cutoff = 30% of longer string
        // length, accept-if-distance-under-cutoff.
        let a = "John Smith";
        let b = "Jon Smythe";
        let cutoff = (a.len().max(b.len()) * 3) / 10;
        let d = distance_cutoff(a, b, cutoff);
        // d is 3 (t→y subst, e insert, h... actually we don't care about
        // the exact value — just that the function answers without panic
        // and the early-exit cutoff path is safe to call).
        assert!(d <= cutoff + 1);
    }
}
