// Load `rust/data/names/symbols.json` for the tagger build path.
//
// The JSON's five top-level keys map 1:1 to the five nested dicts in
// `resources/names/symbols.yml`: each is a `{group_key: [aliases...]}`
// object where the group_key becomes the `Symbol.id` (uppercased by
// the tagger) and the aliases become needles in the AC automaton.
//
// Internal to the Rust crate — no PyO3 surface. Consumed by
// `names::tagger::build_{org,person}_tagger`.

use serde::Deserialize;
use std::collections::HashMap;
use std::sync::LazyLock;

const JSON: &str = include_str!("../../data/names/symbols.json");

#[derive(Debug, Deserialize)]
pub struct NameSymbols {
    pub org_symbols: HashMap<String, Vec<String>>,
    pub org_domains: HashMap<String, Vec<String>>,
    pub person_symbols: HashMap<String, Vec<String>>,
    pub person_nick: HashMap<String, Vec<String>>,
    pub person_name_parts: HashMap<String, Vec<String>>,
}

static DATA: LazyLock<NameSymbols> =
    LazyLock::new(|| serde_json::from_str(JSON).expect("symbols.json parses"));

pub fn data() -> &'static NameSymbols {
    &DATA
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_nonempty_dicts() {
        let d = data();
        assert!(!d.org_symbols.is_empty());
        assert!(!d.org_domains.is_empty());
        assert!(!d.person_symbols.is_empty());
        assert!(!d.person_nick.is_empty());
        // person_name_parts is small (2 entries in current data); check
        // just that it parses, not a specific count.
        let _ = &d.person_name_parts;
    }

    #[test]
    fn org_symbols_has_known_entry() {
        let d = data();
        // Genscripts upper-cases group keys before emission; the
        // tagger does the same on the Symbol::id side, so both match.
        assert!(d.org_symbols.contains_key("AGENCY"));
    }
}
