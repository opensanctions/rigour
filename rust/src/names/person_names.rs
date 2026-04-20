// Person-names corpus loader.
//
// The corpus ships as plain UTF-8 (`rust/data/names/person_names.txt`,
// committed), gets compiled into the binary as zstd-compressed bytes
// by `build.rs`, and is decompressed into a caller-scoped `String` on
// each call. Format: one mapping per line in the shape
//
//     form1, form2, form3 => <group-id>\n
//
// where `<group-id>` is a Wikidata Q-number ("Qxxxx") or an `X`-
// prefixed manual override ID, and `form*` are name variants. See
// `contrib/namesdb/namesdb/export.py::generate_export_lines` for the
// authoritative emission.
//
// No static `LazyLock<String>` cache — the only consumer is the tagger
// builder (`names::tagger`), which runs once per `(TaggerKind, flags,
// cleanup)` combination and drops the decompressed buffer as soon as
// its AC automaton is assembled. Caching ~8.5 MB of decompressed text
// for process life when nobody reads it after tagger build would just
// be dead retention on top of the 2.7 MB compressed copy that already
// lives in `.rodata`.

/// The compressed corpus — produced by `build.rs` from
/// `rust/data/names/person_names.txt`. Empty if the source file was
/// missing at build time (build.rs emits a warning in that case).
const COMPRESSED: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/person_names.txt.zst"));

/// Decompress the corpus into a fresh `String`. Returns empty if
/// `rust/data/names/person_names.txt` was missing at build time.
/// Caller owns the allocation and is expected to drop it once
/// per-line parsing is done — do not stash the result in a static.
pub fn decompressed() -> String {
    if COMPRESSED.is_empty() {
        return String::new();
    }
    let bytes = zstd::decode_all(COMPRESSED).expect("zstd decode person_names.txt.zst");
    String::from_utf8(bytes).expect("person_names.txt is valid UTF-8")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_and_has_expected_shape() {
        let text = decompressed();
        // If the corpus was committed for this build, sanity-check
        // the shape. If build.rs fell through to the empty
        // placeholder (source file absent on a fresh clone), just
        // skip — this test should not fail a clone-and-build-and-
        // test flow before namesdb has dumped.
        if text.is_empty() {
            return;
        }
        let first = text.lines().next().expect("at least one line");
        assert!(
            first.contains(" => "),
            "expected 'forms => id' shape, got {first:?}"
        );
    }

    #[test]
    fn id_prefix_distribution_is_sane() {
        let text = decompressed();
        if text.is_empty() {
            return;
        }
        let mut q_count = 0usize;
        let mut x_count = 0usize;
        let mut other = 0usize;
        for line in text.lines() {
            let Some((_, id)) = line.rsplit_once(" => ") else {
                continue;
            };
            match id.as_bytes().first() {
                Some(b'Q') => q_count += 1,
                Some(b'X') => x_count += 1,
                _ => other += 1,
            }
        }
        // The corpus is dominantly Wikidata QIDs with a small tail of
        // X-prefixed manual overrides. If anything else shows up the
        // format has drifted.
        assert!(q_count > 0, "no Q-prefixed entries");
        assert_eq!(other, 0, "unexpected id prefix in corpus ({other} lines)");
        // Rough shape check: QIDs massively outnumber XIDs.
        assert!(q_count > 10 * x_count);
    }
}
