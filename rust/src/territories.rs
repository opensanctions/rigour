// Territory records loader.
//
// `rust/data/territories/data.jsonl` is the full territory database:
// one JSON record per line, fields `{code, name, full_name, alpha3,
// qid, parent, is_country, is_jurisdiction, is_historical, langs,
// names_strong, names_weak, ...}`. Authoritative emission is
// `genscripts/generate_territories.py::update_data`.
//
// The JSONL ships as plain UTF-8 in git (~783 KiB, diff-friendly when
// the generator regenerates) and gets zstd-compressed at crate-build
// time by `build.rs` (~214 KiB). Decompression is lazy on first call
// to `raw()`. The decompressed `String` lives in a `LazyLock` so
// `&'static str` lifetimes still work for consumers — Python reads
// through the `rigour._core.territories_jsonl()` PyO3 accessor, and
// the Rust tagger parses the same text line-by-line via serde.

use std::sync::LazyLock;

/// The compressed blob — produced by `build.rs` from
/// `rust/data/territories/data.jsonl`. Empty if the source file was
/// missing at build time (build.rs emits a warning).
const COMPRESSED: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/territories.jsonl.zst"));

static DECOMPRESSED: LazyLock<String> = LazyLock::new(|| {
    if COMPRESSED.is_empty() {
        return String::new();
    }
    let bytes = zstd::decode_all(COMPRESSED).expect("zstd decode territories.jsonl.zst");
    String::from_utf8(bytes).expect("territories.jsonl is valid UTF-8")
});

/// Return the full territories JSONL as `&'static str`, lazily decoded
/// on first call. Python-side consumers parse line-by-line with
/// orjson; the Rust tagger reads through serde into typed structs.
pub fn raw() -> &'static str {
    &DECOMPRESSED
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_and_has_records() {
        let text = raw();
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
