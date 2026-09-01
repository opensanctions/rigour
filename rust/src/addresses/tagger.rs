// AC-based address tagger: recognises keyword signifiers
// (`rust/data/addresses/forms.json`) and territory strong names
// (`rust/data/territories/data.jsonl`) in normalized address text.
//
// Needles are normalised with the same flags as the runtime
// haystack (`TAGGER_FLAGS`, no Cleanup) — the needle==haystack
// contract from `names::tagger` applies. One fixed configuration,
// so a single lazily-built tagger instead of a flag-keyed cache.

use std::collections::{BTreeMap, HashMap};
use std::sync::LazyLock;

use crate::territories;
use crate::text::matcher::{Match, Needles};
use crate::text::normalize::{Cleanup, Normalize, normalize};
use crate::text::numbers::numeric_value;
use crate::text::ordinals::ordinals;

/// Normalization applied to needles at build time and expected of
/// the haystack at match time: casefold, then address-tokenize and
/// re-join with single spaces.
pub const TAGGER_FLAGS: Normalize = Normalize::CASEFOLD.union(Normalize::ADDRESS);

/// Classification payload of a matched phrase.
#[derive(Debug, Clone, PartialEq)]
pub enum Tag {
    /// Keyword signifier; payload is the canonical short form.
    Keyword(String),
    /// Ordinal form ("30 th", "1 й", "№ 17"); payload is the number.
    Ordinal(u32),
    /// Territory name; payload is every code the name maps to.
    Territory(Vec<String>),
}

/// Accumulates all sources per phrase before precedence resolution.
#[derive(Default)]
struct Entry {
    keyword: Option<String>,
    ordinal: Option<u32>,
    codes: Vec<String>,
}

struct Builder {
    mapping: HashMap<String, Entry>,
}

impl Builder {
    fn new() -> Self {
        Builder {
            mapping: HashMap::new(),
        }
    }

    fn norm(s: &str) -> Option<String> {
        normalize(s, TAGGER_FLAGS, Cleanup::Noop).filter(|n| !n.is_empty())
    }

    /// First canonical claim on an alias wins — forms.json is
    /// iterated in sorted key order, so collisions resolve
    /// deterministically.
    fn add_keyword(&mut self, alias: &str, canonical: &str) {
        let Some(key) = Self::norm(alias) else {
            return;
        };
        let entry = self.mapping.entry(key).or_default();
        if entry.keyword.is_none() {
            entry.keyword = Some(canonical.to_string());
        }
    }

    /// Only ordinal forms carrying a numeric character are admitted
    /// ("1st", "1-й", "第一"); pure word forms ("First", "один",
    /// "I.") are false-positive-prone as bare tokens.
    fn add_ordinal(&mut self, form: &str, number: u32) {
        if !form.chars().any(|c| numeric_value(c).is_some()) {
            return;
        }
        let Some(key) = Self::norm(form) else {
            return;
        };
        let entry = self.mapping.entry(key).or_default();
        if entry.ordinal.is_none() {
            entry.ordinal = Some(number);
        }
    }

    fn add_territory(&mut self, name: &str, code: &str) {
        let Some(key) = Self::norm(name) else {
            return;
        };
        let entry = self.mapping.entry(key).or_default();
        if !entry.codes.iter().any(|c| c == code) {
            entry.codes.push(code.to_string());
        }
    }

    /// A phrase claimed by several sources resolves keyword, then
    /// ordinal, then territory: signifier readings ("st") are
    /// locally more reliable than an ordinal or territory name
    /// coinciding with one.
    fn finish(self) -> AddressTagger {
        let entries = self.mapping.into_iter().map(|(phrase, entry)| {
            let tag = match (entry.keyword, entry.ordinal) {
                (Some(canonical), _) => Tag::Keyword(canonical),
                (None, Some(number)) => Tag::Ordinal(number),
                (None, None) => Tag::Territory(entry.codes),
            };
            (phrase, tag)
        });
        AddressTagger {
            needles: Needles::build(entries),
        }
    }
}

pub struct AddressTagger {
    needles: Needles<Tag>,
}

impl AddressTagger {
    /// Non-overlapping, boundary-filtered, longest-at-start matches
    /// over pre-normalised text, sorted by start offset. Offsets are
    /// bytes into the haystack.
    pub fn find<'a>(&'a self, text: &'a str) -> Vec<Match<'a, Tag>> {
        self.needles.find_iter(text)
    }
}

const FORMS_JSON: &str = include_str!("../../data/addresses/forms.json");

fn build_tagger() -> AddressTagger {
    let mut b = Builder::new();

    // Keyword forms: every alias and the canonical key itself map
    // to the canonical form, so "blvd" in text tags as blvd too.
    let forms: BTreeMap<String, Vec<String>> =
        serde_json::from_str(FORMS_JSON).expect("rust/data/addresses/forms.json parses");
    for (canonical, aliases) in &forms {
        b.add_keyword(canonical, canonical);
        for alias in aliases {
            b.add_keyword(alias, canonical);
        }
    }

    // Ordinal forms: multi-token after normalization where the
    // tokenizer splits digits out ("30th" → "30 th", "№1" → "№ 1"),
    // so a match re-collapses exactly what the split separated.
    for spec in ordinals() {
        for form in &spec.forms {
            b.add_ordinal(form, spec.number);
        }
    }

    // Strong and weak territory names both tag: weak names
    // (translations/transliterations) measurably improve the
    // address_bench translation slices, and the code-overlap
    // scorer only rewards agreement, so a stray weak-name tag
    // costs little.
    for record in territories::records() {
        b.add_territory(&record.name, &record.code);
        if let Some(full) = &record.full_name {
            b.add_territory(full, &record.code);
        }
        for name in &record.names_strong {
            b.add_territory(name, &record.code);
        }
        for name in &record.names_weak {
            b.add_territory(name, &record.code);
        }
    }

    b.finish()
}

static TAGGER: LazyLock<AddressTagger> = LazyLock::new(build_tagger);

/// The process-wide address tagger, built on first use.
pub fn tagger() -> &'static AddressTagger {
    &TAGGER
}

#[cfg(test)]
mod tests {
    use super::*;

    fn find_one(text: &str) -> Option<Tag> {
        let matches = tagger().find(text);
        assert!(matches.len() <= 1, "expected at most one match: {text}");
        matches.into_iter().next().map(|m| m.payload.clone())
    }

    #[test]
    fn keyword_alias_maps_to_canonical() {
        assert_eq!(
            find_one("boulevard"),
            Some(Tag::Keyword("blvd".to_string()))
        );
    }

    #[test]
    fn canonical_key_is_a_needle() {
        assert_eq!(find_one("blvd"), Some(Tag::Keyword("blvd".to_string())));
    }

    #[test]
    fn cyrillic_alias() {
        assert_eq!(find_one("шоссе"), Some(Tag::Keyword("hwy".to_string())));
    }

    #[test]
    fn multi_token_territory_name() {
        assert_eq!(
            find_one("saudi arabia"),
            Some(Tag::Territory(vec!["sa".to_string()]))
        );
    }

    #[test]
    fn territory_full_name() {
        assert_eq!(
            find_one("syrian arab republic"),
            Some(Tag::Territory(vec!["sy".to_string()]))
        );
    }

    #[test]
    fn boundary_filter_blocks_substring() {
        assert_eq!(find_one("gerard"), None);
    }

    #[test]
    fn keyword_wins_over_territory() {
        let mut b = Builder::new();
        b.add_territory("st", "xx");
        b.add_keyword("st", "st");
        let t = b.finish();
        let matches = t.find("st");
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].payload, &Tag::Keyword("st".to_string()));
    }

    #[test]
    fn territory_codes_merge() {
        let mut b = Builder::new();
        b.add_territory("springfield", "us-il");
        b.add_territory("springfield", "us-mo");
        b.add_territory("springfield", "us-il");
        let t = b.finish();
        let matches = t.find("springfield");
        assert_eq!(
            matches[0].payload,
            &Tag::Territory(vec!["us-il".to_string(), "us-mo".to_string()])
        );
    }

    #[test]
    fn symbol_signifiers_are_needles() {
        // The address tokenizer keeps "№" and "&" as token content,
        // so their forms.yml entries become live needles.
        assert_eq!(find_one("№"), Some(Tag::Keyword("no".to_string())));
        assert_eq!(find_one("&"), Some(Tag::Keyword("&".to_string())));
    }
}
