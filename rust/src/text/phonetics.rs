// Metaphone and Soundex wrappers around the `rphonetic` crate (a pure-Rust port
// of Apache commons-codec's phonetic algorithms). Chosen over vendoring the
// jellyfish Rust source because rphonetic is actively maintained and the
// algorithmic outputs are the stated interest, not source lineage.
//
// Parity note: rphonetic's output may differ from the Python `jellyfish`
// package on edge cases (H/W handling in Soundex, silent letters / GH / CIA /
// SCH in Metaphone). We configure Metaphone with a large max_code_len to avoid
// rphonetic's default 4-char truncation, but any remaining divergences are
// accepted as a consequence of the implementation swap.

use rphonetic::{Encoder, Metaphone, Soundex};

// Jellyfish's metaphone doesn't truncate; rphonetic defaults to 4 characters.
// Use a bound large enough that no realistic input hits it.
const METAPHONE_MAX_LEN: usize = 64;

pub fn metaphone(token: &str) -> String {
    if token.is_empty() {
        return String::new();
    }
    Metaphone::new(Some(METAPHONE_MAX_LEN)).encode(token)
}

pub fn soundex(token: &str) -> String {
    if token.is_empty() {
        return String::new();
    }
    Soundex::default().encode(token)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn metaphone_basic() {
        assert_eq!(metaphone(""), "");
        assert_eq!(metaphone("Robert"), "RBRT");
        assert_eq!(metaphone("Philadelphia"), "FLTLF");
    }

    #[test]
    fn soundex_basic() {
        assert_eq!(soundex(""), "");
        assert_eq!(soundex("Robert"), "R163");
        assert_eq!(soundex("Ashcraft"), "A261");
    }
}
