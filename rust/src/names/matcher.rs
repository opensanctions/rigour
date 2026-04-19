// Generic multi-needle string search with Python-style
// `(?<!\w)X(?!\w)` word boundaries. Used to back:
//
//   - rigour.names.org_types.replace_org_types_compare (payload = target String)
//   - rigour.names.tagging.tag_org_name / tag_person_name (payload = Symbol)
//     [future — not yet wired up]
//
// Consolidates what was previously split between a fancy-regex
// Replacer in org_types and a Python-side `ahocorasick-rs` tagger.
//
// ## Design
//
// Each caller builds a `Needles<T>` from `(String, T)` pairs: the
// string is the pre-normalised form to search for, the T is the
// payload to return on match (e.g. the compare-form target for
// org_types, or a Symbol for the tagger). Keys are deduplicated with
// last-wins semantics to match Python `dict.update` behaviour.
//
// At search time, `find_iter(text)` returns the non-overlapping
// leftmost-longest set of matches that pass the Python boundary
// check. The algorithm:
//
//   1. Walk the AC automaton in `find_overlapping_iter` mode to get
//      every (start, end, pattern_id) triple — O(haystack + matches).
//   2. Drop any match that fails the boundary check (char before
//      match is \w, or char after is \w).
//   3. Sort by (start asc, end desc) so at each start position the
//      longest surviving candidate comes first.
//   4. Greedy-select: walk sorted candidates, take each whose start
//      is >= the end of the previous taken match; skip the rest.
//
// Why overlapping + greedy and not `MatchKind::LeftmostLongest`:
// LeftmostLongest returns only the longest match at the leftmost
// position. If that match fails the post-filter boundary check, a
// shorter match at the same position that WOULD pass is invisible.
// Example: `"public limited co.foo"` — "public limited co." fails
// (followed by \w) but "public limited" at the same start position
// passes. Overlapping iteration surfaces both; greedy-select picks
// the valid one. Cost is negligible at our data sizes (~1k needles,
// ~30-char haystacks, a handful of candidates per call).

use aho_corasick::{AhoCorasick, AhoCorasickBuilder, MatchKind};
use std::collections::HashMap;

/// A multi-needle string search automaton with per-needle payload.
pub struct Needles<T> {
    ac: AhoCorasick,
    payloads: Vec<T>,
}

/// A boundary-passing match returned by `Needles::find_iter`.
pub struct Match<'a, T> {
    pub start: usize,
    pub end: usize,
    pub matched: &'a str,
    pub payload: &'a T,
}

impl<T> Needles<T> {
    /// Build a Needles automaton from `(needle, payload)` pairs.
    ///
    /// Duplicate needles are deduplicated last-wins, matching Python
    /// `dict.update`. Empty needles are silently dropped.
    pub fn build(entries: impl IntoIterator<Item = (String, T)>) -> Self {
        // Dedup by key. We can't use HashMap<String, T> directly
        // because T may not be Hash; use a positional map
        // String → index-into-vec, overwrite on collision.
        let mut keys: Vec<String> = Vec::new();
        let mut payloads: Vec<T> = Vec::new();
        let mut index: HashMap<String, usize> = HashMap::new();
        for (key, payload) in entries {
            if key.is_empty() {
                continue;
            }
            if let Some(&i) = index.get(&key) {
                payloads[i] = payload;
            } else {
                index.insert(key.clone(), keys.len());
                keys.push(key);
                payloads.push(payload);
            }
        }
        let ac = AhoCorasickBuilder::new()
            // ASCII-only case-insensitive matching is enough: callers
            // pre-normalise with CASEFOLD so needles and haystack are
            // both lowercase already. The flag is belt-and-suspenders.
            .ascii_case_insensitive(true)
            // Standard match kind is required for overlapping
            // iteration (LeftmostFirst/LeftmostLongest disallow it).
            // We implement leftmost-longest ourselves via greedy
            // selection on the overlapping match set.
            .match_kind(MatchKind::Standard)
            .build(&keys)
            .expect("needle automaton builds");
        Self { ac, payloads }
    }

    /// Return the non-overlapping, leftmost-longest, boundary-passing
    /// matches in `text`. Materialised as a Vec since we have to
    /// collect + sort internally anyway; for our call sizes (< 100
    /// matches per call) the alloc is negligible.
    pub fn find_iter<'a>(&'a self, text: &'a str) -> Vec<Match<'a, T>> {
        let bytes = text.as_bytes();

        // Step 1–2: collect boundary-passing candidates.
        let mut cands: Vec<(usize, usize, usize)> = Vec::new();
        for m in self.ac.find_overlapping_iter(text) {
            let start = m.start();
            let end = m.end();
            if boundary_ok(bytes, start, end) {
                cands.push((start, end, m.pattern().as_usize()));
            }
        }

        // Step 3: sort by (start asc, end desc). Ties on (start, end)
        // shouldn't happen because keys are deduped in build(); if
        // they do, pattern_id ordering is a stable but arbitrary
        // tiebreak — same behaviour as Python `dict`-backed Replacer.
        cands.sort_by(|a, b| a.0.cmp(&b.0).then_with(|| b.1.cmp(&a.1)));

        // Step 4: greedy select non-overlapping.
        let mut out: Vec<Match<'a, T>> = Vec::with_capacity(cands.len());
        let mut last_end = 0usize;
        for (start, end, pid) in cands {
            if start >= last_end {
                last_end = end;
                out.push(Match {
                    start,
                    end,
                    matched: &text[start..end],
                    payload: &self.payloads[pid],
                });
            }
        }
        out
    }
}

/// True iff the match at `[start, end)` is flanked by non-word chars
/// or the string edge — Python's `(?<!\w)X(?!\w)` semantics.
fn boundary_ok(bytes: &[u8], start: usize, end: usize) -> bool {
    let before_ok = start == 0 || !is_word_char_before(bytes, start);
    let after_ok = end == bytes.len() || !is_word_char_after(bytes, end);
    before_ok && after_ok
}

fn is_word_char_before(bytes: &[u8], pos: usize) -> bool {
    // Step back to the start of the codepoint that ends at `pos`.
    let mut i = pos - 1;
    while i > 0 && (bytes[i] & 0b1100_0000) == 0b1000_0000 {
        i -= 1;
    }
    if bytes[i] < 0x80 {
        return is_ascii_word(bytes[i]);
    }
    decode_is_word(&bytes[i..pos])
}

fn is_word_char_after(bytes: &[u8], pos: usize) -> bool {
    if bytes[pos] < 0x80 {
        return is_ascii_word(bytes[pos]);
    }
    let mut j = pos + 1;
    while j < bytes.len() && (bytes[j] & 0b1100_0000) == 0b1000_0000 {
        j += 1;
    }
    decode_is_word(&bytes[pos..j])
}

#[inline]
fn is_ascii_word(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

fn decode_is_word(utf8: &[u8]) -> bool {
    match std::str::from_utf8(utf8)
        .ok()
        .and_then(|s| s.chars().next())
    {
        Some(c) => c.is_alphanumeric() || c == '_',
        None => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn build<'a>(entries: &[(&'a str, &'a str)]) -> Needles<String> {
        Needles::build(entries.iter().map(|(k, v)| (k.to_string(), v.to_string())))
    }

    fn match_spans(n: &Needles<String>, text: &str) -> Vec<(usize, usize, String)> {
        n.find_iter(text)
            .into_iter()
            .map(|m| (m.start, m.end, m.payload.clone()))
            .collect()
    }

    #[test]
    fn basic_word_edged_match() {
        let n = build(&[("llc", "LLC"), ("inc", "INC")]);
        assert_eq!(
            match_spans(&n, "acme llc holdings"),
            vec![(5, 8, "LLC".into())]
        );
    }

    #[test]
    fn respects_word_boundary_inside_word() {
        // 'llc' appears inside 'bellcorp' — must not match.
        let n = build(&[("llc", "LLC")]);
        assert_eq!(match_spans(&n, "bellcorp holdings"), vec![]);
    }

    #[test]
    fn trailing_punct_at_eos() {
        // Alias ends in '.', match at end-of-string — boundary check
        // passes because EOS-edge is treated as \W.
        let n = build(&[("inc.", "INC")]);
        assert_eq!(match_spans(&n, "apple inc."), vec![(6, 10, "INC".into())]);
    }

    #[test]
    fn trailing_punct_followed_by_word_char_fails() {
        // Alias "inc." followed by \w should NOT match — Python's
        // (?!\w) semantics.
        let n = build(&[("inc.", "INC")]);
        assert_eq!(match_spans(&n, "apple inc.x"), vec![]);
    }

    #[test]
    fn leading_punct_after_word_char_fails() {
        // Alias "-gmbh" inside a word ("foo-gmbh") — preceding \w
        // must fail the (?<!\w) check.
        let n = build(&[("-gmbh", "GMBH")]);
        assert_eq!(match_spans(&n, "foo-gmbh"), vec![]);
    }

    #[test]
    fn leading_punct_after_non_word_passes() {
        // Alias "-gmbh" after a space is fine.
        let n = build(&[("-gmbh", "GMBH")]);
        assert_eq!(match_spans(&n, "foo -gmbh"), vec![(4, 9, "GMBH".into())]);
    }

    #[test]
    fn leftmost_longest_prefers_longer_alias() {
        // Both "llc" and "llc holdings" could match at position 5;
        // the longer one wins.
        let n = build(&[("llc", "LLC"), ("llc holdings", "LLCH")]);
        assert_eq!(
            match_spans(&n, "acme llc holdings"),
            vec![(5, 17, "LLCH".into())]
        );
    }

    #[test]
    fn pathological_shorter_saves_longer_fails() {
        // The case motivating the overlapping+greedy design:
        // "public limited co.foo" — the long alias fails boundary
        // (followed by \w), but the short alias at the same start
        // position passes. Must surface the shorter one.
        let n = build(&[("public limited co.", "PLC_DOT"), ("public limited", "PL")]);
        assert_eq!(
            match_spans(&n, "public limited co.foo"),
            vec![(0, 14, "PL".into())]
        );
    }

    #[test]
    fn empty_needle_ignored() {
        let n = build(&[("", "EMPTY"), ("llc", "LLC")]);
        assert_eq!(match_spans(&n, "acme llc"), vec![(5, 8, "LLC".into())]);
    }

    #[test]
    fn dedup_last_wins() {
        // Two entries with the same key — second payload wins,
        // matching Python dict.update semantics.
        let n = build(&[("llc", "FIRST"), ("llc", "SECOND")]);
        assert_eq!(match_spans(&n, "acme llc"), vec![(5, 8, "SECOND".into())]);
    }

    #[test]
    fn unicode_boundary_works() {
        // Non-ASCII word chars: Chinese characters are \w. A match
        // adjacent to them should fail the boundary check.
        let n = build(&[("co", "CO")]);
        // "公co司" — 'co' inside two CJK word chars — boundary fails.
        assert_eq!(match_spans(&n, "公co司"), vec![]);
        // "co" alone at EOS — passes.
        assert_eq!(match_spans(&n, "公 co"), vec![(4, 6, "CO".into())]);
    }
}
