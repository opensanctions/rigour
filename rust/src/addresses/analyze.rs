// Address analysis pass: normalize → tokenize → tag → classify.
// Produces the `Address` consumed by the comparison scorer. No
// PyO3 surface — the Python entry points arrive with the scorer.

use crate::addresses::tagger::{TAGGER_FLAGS, Tag, tagger};
use crate::addresses::token::{AddressToken, TokenClass};
use crate::text::normalize::{Cleanup, normalize};
use crate::text::numbers::string_number;
use crate::text::scripts::text_scripts;

/// An analyzed address: classed tokens plus the scripts present in
/// the normalized text (feeds the cross-script evidence cap).
#[derive(Debug, Clone, PartialEq)]
pub struct Address {
    /// Classed tokens in input order; tagged multi-token phrases
    /// are collapsed into single tokens.
    pub tokens: Vec<AddressToken>,
    /// Distinguishing scripts of the normalized text, in first-
    /// appearance order.
    pub scripts: Vec<&'static str>,
}

/// Analyze a raw address string into classed tokens.
///
/// Returns `None` when normalization leaves nothing to analyze
/// (empty or punctuation-only input).
pub fn analyze(text: &str) -> Option<Address> {
    let norm = normalize(text, TAGGER_FLAGS, Cleanup::Noop)?;
    let scripts = text_scripts(&norm);

    // Token byte ranges in the space-joined normalized string.
    let mut bounds: Vec<(usize, usize)> = Vec::new();
    let mut offset = 0;
    for tok in norm.split(' ') {
        bounds.push((offset, offset + tok.len()));
        offset += tok.len() + 1;
    }

    // Matches come back sorted by start, non-overlapping. Tagged
    // phrases must align with token boundaries to collapse; the
    // boundary filter makes misalignment rare (only possible around
    // non-alphanumeric chars inside a token), and misaligned
    // matches are dropped rather than splitting a token.
    let matches = tagger().find(&norm);
    let mut tokens: Vec<AddressToken> = Vec::new();
    let mut mi = 0;
    let mut ti = 0;
    while ti < bounds.len() {
        let (start, end) = bounds[ti];
        while mi < matches.len() && matches[mi].start < start {
            mi += 1;
        }
        if mi < matches.len() && matches[mi].start == start {
            let m = &matches[mi];
            let span = bounds[ti..].iter().position(|&(_, e)| e == m.end);
            if let Some(count) = span {
                let class = match m.payload {
                    Tag::Keyword(canonical) => TokenClass::Keyword {
                        canonical: canonical.clone(),
                    },
                    Tag::Territory(codes) => TokenClass::Territory {
                        codes: codes.clone(),
                    },
                };
                tokens.push(AddressToken::new(norm[start..m.end].to_string(), class));
                ti += count + 1;
                mi += 1;
                continue;
            }
            mi += 1;
        }
        let surface = &norm[start..end];
        let class = match string_number(surface) {
            Some(value) => TokenClass::Number { value },
            None => TokenClass::Text,
        };
        tokens.push(AddressToken::new(surface.to_string(), class));
        ti += 1;
    }

    Some(Address { tokens, scripts })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn classes(addr: &Address) -> Vec<(&str, &TokenClass)> {
        addr.tokens
            .iter()
            .map(|t| (t.surface.as_str(), &t.class))
            .collect()
    }

    #[test]
    fn empty_and_punctuation_only() {
        assert_eq!(analyze(""), None);
        assert_eq!(analyze("  ,,, --- "), None);
    }

    #[test]
    fn keyword_dense_us_address() {
        let addr = analyze("2221 30th Ave S Fargo, ND 58103-5872").unwrap();
        let got = classes(&addr);
        assert_eq!(got[0], ("2221", &TokenClass::Number { value: 2221.0 }));
        assert_eq!(got[1].0, "30th");
        assert_eq!(got[1].1, &TokenClass::Text);
        assert_eq!(
            got[2],
            (
                "ave",
                &TokenClass::Keyword {
                    canonical: "av".to_string()
                }
            )
        );
        assert_eq!(got[4].0, "fargo");
        // Bare state codes are not territory strong names.
        assert_eq!(got[5], ("nd", &TokenClass::Text));
        // The zip+4 splits into two number tokens.
        assert_eq!(got[6], ("58103", &TokenClass::Number { value: 58103.0 }));
        assert_eq!(got[7], ("5872", &TokenClass::Number { value: 5872.0 }));
        assert_eq!(addr.scripts, vec!["Latin"]);
    }

    #[test]
    fn cyrillic_address() {
        let addr = analyze("Воткинское шоссе, д. 170, Ижевск").unwrap();
        let got = classes(&addr);
        assert_eq!(got[0].1, &TokenClass::Text);
        assert_eq!(
            got[1],
            (
                "шоссе",
                &TokenClass::Keyword {
                    canonical: "hwy".to_string()
                }
            )
        );
        // Bare "д" is not in the forms table (only "дом" is).
        assert_eq!(got[2], ("д", &TokenClass::Text));
        assert_eq!(got[3], ("170", &TokenClass::Number { value: 170.0 }));
        assert_eq!(addr.tokens[0].ascii.as_deref(), Some("votkinskoe"));
        assert_eq!(addr.scripts, vec!["Cyrillic"]);
    }

    #[test]
    fn multi_token_territory_collapses() {
        let addr = analyze("P.O. Box 7155, Damascus, Syrian Arab Republic").unwrap();
        let last = addr.tokens.last().unwrap();
        assert_eq!(last.surface, "syrian arab republic");
        assert_eq!(
            last.class,
            TokenClass::Territory {
                codes: vec!["sy".to_string()]
            }
        );
    }

    #[test]
    fn compound_number_splits() {
        let addr = analyze("ul. Lenina 17/1").unwrap();
        let got = classes(&addr);
        let numbers: Vec<_> = got
            .iter()
            .filter(|(_, c)| matches!(c, TokenClass::Number { .. }))
            .collect();
        assert_eq!(numbers.len(), 2);
        assert_eq!(numbers[0].0, "17");
        assert_eq!(numbers[1].0, "1");
    }

    #[test]
    fn mixed_script_reported() {
        let addr = analyze("Votkinskoe shosse 170, Ижевск").unwrap();
        assert_eq!(addr.scripts, vec!["Latin", "Cyrillic"]);
    }
}
