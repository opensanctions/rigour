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
// time by `build.rs` (~214 KiB).
//
// No static `LazyLock<String>` cache — each `decompressed()` call
// returns a fresh owned `String`. Both consumers are one-shot:
// Python's `rigour.territories.*` reads via `@cache`-decorated index
// builders (so exactly one FFI hop per process), and the Rust tagger
// walks the lines once per `(TaggerKind, flags, cleanup)` cache miss.
// A persistent Rust-side copy would just duplicate what's already in
// Python's cached PyString / the tagger's AC automaton.

/// The compressed blob — produced by `build.rs` from
/// `rust/data/territories/data.jsonl`. Empty if the source file was
/// missing at build time (build.rs emits a warning).
const COMPRESSED: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/territories.jsonl.zst"));

/// Decompress the JSONL into a fresh `String`. Returns empty if
/// `rust/data/territories/data.jsonl` was missing at build time.
/// Caller owns the allocation — do not stash the result in a static.
/// PyO3 boundary: returning `String` to Python makes a fresh
/// `PyString` and drops the Rust side, leaving only Python's copy.
pub fn decompressed() -> String {
    if COMPRESSED.is_empty() {
        return String::new();
    }
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
