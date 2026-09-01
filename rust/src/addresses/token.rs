// Classed address tokens — the unit of the analyzed `Address`.
//
// Mirrors the `NamePart` shape: a token carries its surface form,
// a precomputed narrow transliteration, and a class whose payload
// *is* the canonical form (parsed value, canonical keyword form,
// territory codes). There is no generic "normalized" field.

use crate::text::translit::maybe_ascii;

/// Classification of an address token, carrying its canonical form.
#[derive(Debug, Clone, PartialEq)]
pub enum TokenClass {
    /// Numeric token; `digits` is the canonical ASCII digit string
    /// derived at analysis time — folded surface digits for parsed
    /// numbers (leading zeros preserved: "007" stays "007", "１７"
    /// becomes "17"), the ordinal's value for tagged ordinal
    /// phrases ("30 th" → "30").
    Number { digits: String },
    /// Address signifier recognised from the keyword forms table;
    /// `canonical` is the short form key ("blvd" for "boulevard").
    Keyword { canonical: String },
    /// Recognised territory name; `codes` holds every territory
    /// the name can refer to (ambiguous names map to several).
    Territory { codes: Vec<String> },
    /// Cross-language translation term ("peremohy"/"pobedy" →
    /// "victory"). No tagging source populates this yet — the
    /// terms resource lands with scorer tuning.
    Term { symbol: String },
    /// Unrecognised free text — street names, building names,
    /// localities outside the territories DB.
    Text,
}

/// A single analyzed token of an address string.
#[derive(Debug, Clone, PartialEq)]
pub struct AddressToken {
    /// Token text from the normalized (casefolded, tokenized)
    /// input. Multi-token matches collapse into one token whose
    /// surface is the whole matched phrase ("saudi arabia").
    pub surface: String,
    /// Narrow transliteration of `surface` where it differs:
    /// `None` when the surface is already ASCII or its script is
    /// outside the admitted set (Latin, Cyrillic, Greek, Armenian,
    /// Georgian, Hangul).
    pub ascii: Option<String>,
    /// Token classification, carrying the canonical form.
    pub class: TokenClass,
}

impl AddressToken {
    /// Build a token, eagerly computing the transliterated form.
    pub fn new(surface: String, class: TokenClass) -> Self {
        let translit = maybe_ascii(&surface, true);
        let ascii = if translit.is_empty() || translit == surface {
            None
        } else {
            Some(translit)
        };
        AddressToken {
            surface,
            ascii,
            class,
        }
    }

    /// Best-effort matchable form: the transliteration when one
    /// exists, the surface otherwise (covers both already-ASCII
    /// and non-admitted-script tokens).
    pub fn comparable(&self) -> &str {
        self.ascii.as_deref().unwrap_or(&self.surface)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ascii_none_for_latin_surface() {
        let tok = AddressToken::new("fargo".to_string(), TokenClass::Text);
        assert_eq!(tok.ascii, None);
        assert_eq!(tok.comparable(), "fargo");
    }

    #[test]
    fn ascii_filled_for_cyrillic() {
        let tok = AddressToken::new("шоссе".to_string(), TokenClass::Text);
        assert_eq!(tok.ascii.as_deref(), Some("sosse"));
        assert_eq!(tok.comparable(), "sosse");
    }

    #[test]
    fn ascii_none_for_cjk() {
        let tok = AddressToken::new("北京".to_string(), TokenClass::Text);
        assert_eq!(tok.ascii, None);
        assert_eq!(tok.comparable(), "北京");
    }

    #[test]
    fn number_payload_keeps_surface() {
        let tok = AddressToken::new(
            "007".to_string(),
            TokenClass::Number {
                digits: "007".to_string(),
            },
        );
        assert_eq!(tok.surface, "007");
        assert_eq!(
            tok.class,
            TokenClass::Number {
                digits: "007".to_string()
            }
        );
    }
}
