// Address fingerprint: a deterministic keying serialization of the
// analyzed address. Hard normalization per token class — numbers as
// canonical digit strings, keywords as canonical forms, unambiguous
// territory names as codes — so equivalent renderings key
// identically. Token order is preserved: sorting was measured on the
// collapse harness (contrib/address_bench) and rejected — it merges
// transposed-number pairs ("d 17 str 1" / "d 1 str 17"), which a
// keying surface must keep distinct. Same verdict for dropping
// keyword tokens and for serializing ambiguous territory code sets;
// the numbers live in the bench README's collapse log.

use crate::addresses::analyze::analyze_cached;
use crate::addresses::token::{AddressToken, TokenClass};

fn token_form(token: &AddressToken) -> String {
    match &token.class {
        TokenClass::Number { digits } => digits.clone(),
        TokenClass::Keyword { canonical } => canonical.clone(),
        TokenClass::Term { symbol } => symbol.clone(),
        TokenClass::Territory { codes } if codes.len() == 1 => codes[0].clone(),
        TokenClass::Territory { .. } | TokenClass::Text => token.comparable().to_string(),
    }
}

/// Serialize an address string into a keying fingerprint.
///
/// Returns `None` when analysis yields nothing (empty or
/// punctuation-only input). Output is ASCII except free-text tokens
/// in scripts outside the narrow transliteration set (CJK, Arabic,
/// …), which pass through in native script.
pub fn fingerprint(text: &str) -> Option<String> {
    let addr = analyze_cached(text)?;
    let parts: Vec<String> = addr.tokens.iter().map(token_form).collect();
    if parts.is_empty() {
        None
    } else {
        Some(parts.join(" "))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_input_is_none() {
        assert_eq!(fingerprint(""), None);
        assert_eq!(fingerprint(" ,,, --- "), None);
    }

    #[test]
    fn keyword_canonicalization_collapses_abbreviations() {
        let full = fingerprint("Main Boulevard 5");
        let abbr = fingerprint("Main Blvd. 5");
        assert!(full.is_some());
        assert_eq!(full, abbr);
    }

    #[test]
    fn territory_code_collapses_name_variants() {
        let long = fingerprint("Damascus, Syrian Arab Republic").unwrap();
        let short = fingerprint("Damascus, Syria").unwrap();
        assert_eq!(long, short);
        assert!(long.ends_with(" sy"));
    }

    #[test]
    fn number_forms_collapse() {
        assert_eq!(fingerprint("д. №17"), fingerprint("d 17"));
    }

    #[test]
    fn neardupe_transpositions_stay_distinct() {
        assert_ne!(fingerprint("Д. 17 СТР. 1"), fingerprint("Д. 1 СТР. 17"));
    }

    #[test]
    fn reordered_fields_stay_distinct() {
        // The documented cost of preserving order: reordered
        // renderings do not key identically.
        assert_ne!(
            fingerprint("58103 Fargo, Main Str. 17"),
            fingerprint("Main Street 17, Fargo 58103")
        );
    }

    #[test]
    fn cyrillic_transliterates_to_ascii() {
        let fp = fingerprint("Воткинское шоссе, д. 170").unwrap();
        assert!(fp.is_ascii());
        assert!(fp.contains("votkinskoe"));
        assert!(fp.contains("170"));
    }

    #[test]
    fn cjk_passes_through_natively() {
        let fp = fingerprint("北京市 100022").unwrap();
        assert!(!fp.is_ascii());
        assert!(fp.contains("100022"));
    }
}
