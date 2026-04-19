// Rust-side ownership of `resources/text/ordinals.yml` → exposes
// `ordinals_dict()` returning `dict[int, list[str]]` to Python. The
// shape matches Python consumer expectations (`.items()` iteration in
// `rigour/names/tagging.py:75` and `rigour/addresses/normalize.py:104`).
// See `plans/rust-tagger.md` step 4 for the migration.
//
// The JSON on disk is an array of `{number, forms}` records (see
// `genscripts/generate_text.py::generate_ordinals`); we deserialise
// to a Vec and materialise the HashMap on each accessor call since
// Python takes ownership.

use serde::Deserialize;
use std::collections::HashMap;
use std::sync::LazyLock;

#[derive(Debug, Deserialize)]
pub struct OrdinalSpec {
    pub number: u32,
    pub forms: Vec<String>,
}

const JSON: &str = include_str!("../../data/text/ordinals.json");

static DATA: LazyLock<Vec<OrdinalSpec>> = LazyLock::new(|| {
    serde_json::from_str(JSON).expect("rust/data/text/ordinals.json parses")
});

/// Ordinals as a `{number: [forms...]}` map — matches the Python
/// consumer's `ORDINALS.items()` iteration pattern.
pub fn ordinals_dict() -> HashMap<u32, Vec<String>> {
    DATA.iter()
        .map(|o| (o.number, o.forms.clone()))
        .collect()
}

/// Pure-Rust accessor for the raw spec list. Used by the future
/// Rust tagger build path (step 8 of `plans/rust-tagger.md`), which
/// iterates without needing a HashMap.
pub fn ordinals() -> &'static [OrdinalSpec] {
    &DATA
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn data_loads() {
        let d = ordinals_dict();
        assert!(!d.is_empty());
        // ordinal 1 ("one", "1st", "первый", ...) should always have
        // multiple forms across our target languages.
        assert!(d.get(&1).map(|v| v.len() > 5).unwrap_or(false));
    }

    #[test]
    fn spec_list_mirrors_dict() {
        assert_eq!(ordinals().len(), ordinals_dict().len());
    }
}
