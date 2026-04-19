// Rust-side ownership of `resources/text/stopwords.yml` → exposes
// three flat wordlists to Python via `rigour._core.stopwords_list`
// / `nullwords_list` / `nullplaces_list`. The Python-side consumer in
// `rigour/text/stopwords.py` reads these once at import time and
// builds its own `@cache`d normalised sets (one per normalizer) on
// top. See `plans/rust-tagger.md` step 2 for the migration.

use serde::Deserialize;
use std::sync::LazyLock;

#[derive(Debug, Deserialize)]
struct TextStopwords {
    stopwords: Vec<String>,
    nullwords: Vec<String>,
    nullplaces: Vec<String>,
}

const JSON: &str = include_str!("../../data/text/stopwords.json");

static DATA: LazyLock<TextStopwords> = LazyLock::new(|| {
    serde_json::from_str(JSON).expect("rust/data/text/stopwords.json parses")
});

pub fn stopwords_list() -> Vec<String> {
    DATA.stopwords.clone()
}

pub fn nullwords_list() -> Vec<String> {
    DATA.nullwords.clone()
}

pub fn nullplaces_list() -> Vec<String> {
    DATA.nullplaces.clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn data_loads_and_is_nonempty() {
        assert!(!stopwords_list().is_empty());
        assert!(!nullwords_list().is_empty());
        assert!(!nullplaces_list().is_empty());
    }

    #[test]
    fn lists_are_sorted() {
        let s = stopwords_list();
        for pair in s.windows(2) {
            assert!(pair[0] <= pair[1], "stopwords not sorted at {:?}", pair);
        }
    }
}
