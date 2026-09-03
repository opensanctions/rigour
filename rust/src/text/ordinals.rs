// Rust-side ownership of `resources/text/ordinals.yml` → exposes
// `ordinals_dict()` returning `dict[int, list[str]]` to Python.
// The dict-of-lists shape matches the iteration pattern in
// `rigour.addresses.normalize` and the Rust tagger build path.
//
// The JSON on disk is an array of `{number, forms}` records (see
// `genscripts/generate_text.py::generate_ordinals`), zstd-compressed
// into OUT_DIR by `build.rs`. No resident static: every consumer
// caches downstream (tagger builds, the Python dict).

use serde::Deserialize;
use std::collections::HashMap;

#[derive(Debug, Deserialize)]
pub struct OrdinalSpec {
    pub number: u32,
    pub forms: Vec<String>,
}

const ORDINALS_ZST: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/ordinals.json.zst"));

/// Decode the spec list into a fresh, caller-owned Vec — do not
/// stash the result in a static.
pub fn ordinals() -> Vec<OrdinalSpec> {
    let bytes = zstd::decode_all(ORDINALS_ZST).expect("zstd decode ordinals.json.zst");
    serde_json::from_slice(&bytes).expect("ordinals.json parses")
}

/// Ordinals as a `{number: [forms...]}` map — matches the Python
/// consumer's `ORDINALS.items()` iteration pattern.
pub fn ordinals_dict() -> HashMap<u32, Vec<String>> {
    ordinals()
        .into_iter()
        .map(|o| (o.number, o.forms))
        .collect()
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
