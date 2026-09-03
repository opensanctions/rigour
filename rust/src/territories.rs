// Territory records loader.
//
// `rust/data/territories/data.jsonl` is the full territory database:
// one JSON record per line, fields `{code, name, full_name, alpha3,
// qid, parent, is_country, is_jurisdiction, is_historical, langs,
// names_strong, names_weak, ...}`. Authoritative emission is
// `genscripts/generate_territories.py::update_data`.
//
// The JSONL ships as plain UTF-8 in git (diff-friendly when the
// generator regenerates) and is zstd-compressed by `build.rs`.
//
// No static `LazyLock<String>` cache — each `decompressed()` call
// returns a fresh owned `String`; all consumers are one-shot reads
// behind their own caches (Python's `@cache`-decorated index
// builders, the Rust tagger builds).

use serde::Deserialize;

/// The compressed blob — produced by `build.rs` from
/// `rust/data/territories/data.jsonl` (build fails if the source
/// file is missing).
const COMPRESSED: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/territories.jsonl.zst"));

/// Fields from the territory JSONL that Rust-side consumers read —
/// everything else is consumed by `rigour.territories.*` on the
/// Python side and ignored here.
#[derive(Debug, Deserialize)]
pub struct TerritoryRecord {
    /// Lower-case territory code, e.g. `ru`, `us-nd`.
    pub code: String,
    /// Canonical display name.
    pub name: String,
    /// Disambiguated long name, e.g. "Moscow (Russia)".
    pub full_name: Option<String>,
    /// Code of the containing territory, e.g. `ru` for `ru-mow`.
    pub parent: Option<String>,
    /// Unambiguous name aliases, safe for high-precision tagging.
    #[serde(default)]
    pub names_strong: Vec<String>,
    /// Translations and transliterations (CLDR-derived) — broad
    /// recall, more false-positive-prone than `names_strong`;
    /// consumers choose per use case.
    #[serde(default)]
    pub names_weak: Vec<String>,
}

/// Parse the full territory database into records, skipping
/// malformed lines defensively. Allocates fresh on every call —
/// consumers are one-shot builders (see the no-cache note above),
/// and the decompressed corpus drops before this returns.
pub fn records() -> Vec<TerritoryRecord> {
    let corpus = decompressed();
    corpus
        .lines()
        .filter(|line| !line.is_empty())
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect()
}

/// Decompress the JSONL into a fresh `String`. Caller owns the
/// allocation — do not stash the result in a static. PyO3 boundary:
/// returning `String` to Python makes a fresh `PyString` and drops
/// the Rust side, leaving only Python's copy.
pub fn decompressed() -> String {
    let bytes = zstd::decode_all(COMPRESSED).expect("zstd decode territories.jsonl.zst");
    String::from_utf8(bytes).expect("territories.jsonl is valid UTF-8")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_and_has_records() {
        let text = decompressed();
        assert!(!text.is_empty());
        let lines: Vec<&str> = text.lines().filter(|l| !l.is_empty()).collect();
        assert!(
            lines.len() > 100,
            "expected >100 territory records, got {}",
            lines.len()
        );
        // Every line should be a JSON object starting with `{`.
        for line in &lines {
            assert!(
                line.starts_with('{'),
                "expected JSON object per line, got: {}",
                &line[..line.len().min(40)]
            );
        }
    }
}
