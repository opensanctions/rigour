// Rust port of `rigour.names.org_types.*`.
//
// Source data: rust/data/names/org_types.json (generated from
// resources/names/org_types.yml by genscripts/generate_names.py).
// The JSON is indented on disk for reviewability; build.rs
// zstd-compresses it into OUT_DIR and this module decodes on first
// use. Exposes the four public org-type functions: replace_compare,
// replace_display, remove, extract. All four go through the shared
// `names::matcher::Needles<T>` substrate (Aho-Corasick + Python-style
// `(?<!\w)X(?!\w)` boundaries); differences live in which mapping
// the Replacer is built from.
//
// ## Three replacer kinds
//
// - Compare: alias → compare-form (or display-form if `compare` is
//   absent). `compare: ""` = removal. The display-form itself is
//   also added to the mapping so e.g. `replace("LLC")` → target.
//   Clashes (same alias → different targets) are dropped, matching
//   the Python `_compare_replacer` behaviour.
// - Generic: alias → generic-form. Skips specs without a `generic`
//   field. Display-form added as a lookup too.
// - Display: alias → display-form. Skips specs without `display`,
//   skips aliases whose case-preserving form equals their display
//   form (trivial identity — case variants like "GMBH" → "GmbH" are
//   NOT identities, they canonicalise case), pops on clash.
//   Display-form is NOT added as a lookup (matching Python's
//   `_display_replacer`).
//
// ## Flag-keyed cache
//
// Each `(ReplacerKind, Normalize, Cleanup)` combination yields one
// compiled Replacer. First access pays the build cost; subsequent
// calls hit the cache. Same lifecycle as Python's `@cache`-decorated
// replacers.

use icu::casemap::CaseMapper;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, LazyLock, RwLock};

use crate::names::matcher::Needles;
use crate::text::normalize::{Cleanup, Normalize, SquashAction, normalize, squash_action};

#[derive(Debug, Deserialize)]
pub(crate) struct OrgTypeSpec {
    #[serde(default)]
    pub(crate) display: Option<String>,
    #[serde(default)]
    pub(crate) compare: Option<String>,
    #[serde(default)]
    pub(crate) generic: Option<String>,
    #[serde(default)]
    pub(crate) aliases: Vec<String>,
}

const ORG_TYPES_ZST: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/org_types.json.zst"));

pub(crate) static ORG_TYPE_SPECS: LazyLock<Vec<OrgTypeSpec>> = LazyLock::new(|| {
    if ORG_TYPES_ZST.is_empty() {
        return Vec::new();
    }
    let bytes = zstd::decode_all(ORG_TYPES_ZST).expect("zstd decode org_types.json.zst");
    serde_json::from_slice(&bytes).expect("org_types.json parses")
});

/// Selects which mapping (alias → target) the Replacer is built from.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ReplacerKind {
    Compare,
    Display,
    Generic,
}

pub struct Replacer {
    needles: Needles<String>,
}

impl Replacer {
    /// Match-and-substitute. Empty result + non-empty input falls
    /// back to the original text (Python `replacer(name) or name`).
    fn replace(&self, text: &str) -> String {
        let mut out = String::with_capacity(text.len());
        let mut cursor = 0;
        for m in self.needles.find_iter(text) {
            out.push_str(&text[cursor..m.start]);
            out.push_str(m.payload);
            cursor = m.end;
        }
        out.push_str(&text[cursor..]);
        if out.is_empty() && !text.is_empty() {
            text.to_string()
        } else {
            out
        }
    }

    /// Match-and-remove. Every match is replaced with `replacement`.
    /// No fallback — matches Python `replacer.remove(text, replacement)`.
    fn remove(&self, text: &str, replacement: &str) -> String {
        let mut out = String::with_capacity(text.len());
        let mut cursor = 0;
        for m in self.needles.find_iter(text) {
            out.push_str(&text[cursor..m.start]);
            out.push_str(replacement);
            cursor = m.end;
        }
        out.push_str(&text[cursor..]);
        out
    }

    /// Return (matched_text, target) pairs for every match.
    fn extract(&self, text: &str) -> Vec<(String, String)> {
        self.needles
            .find_iter(text)
            .into_iter()
            .map(|m| (m.matched.to_string(), m.payload.clone()))
            .collect()
    }
}

fn norm_fn(flags: Normalize, cleanup: Cleanup) -> impl Fn(&str) -> Option<String> {
    move |s: &str| normalize(s, flags, cleanup)
}

/// Build the Compare replacer — mirrors Python `_compare_replacer`.
fn build_compare(flags: Normalize, cleanup: Cleanup) -> Replacer {
    let norm = norm_fn(flags, cleanup);
    let mut mapping: HashMap<String, String> = HashMap::new();
    let mut seen_targets: HashMap<String, String> = HashMap::new();
    let mut clashes: HashSet<String> = HashSet::new();

    for spec in ORG_TYPE_SPECS.iter() {
        let display_norm = spec.display.as_deref().and_then(&norm);
        // `compare: ""` means "remove this org type" — an intentional
        // empty target. Absent `compare` falls back to display.
        let compare_norm = match spec.compare.as_deref() {
            Some("") => Some(String::new()),
            Some(s) => norm(s),
            None => display_norm.clone(),
        };
        let Some(compare_norm) = compare_norm else {
            continue;
        };

        for alias in &spec.aliases {
            let Some(alias_norm) = norm(alias) else {
                continue;
            };
            if let Some(prev) = seen_targets.get(&alias_norm) {
                if prev != &compare_norm {
                    clashes.insert(alias_norm.clone());
                }
            } else {
                seen_targets.insert(alias_norm.clone(), compare_norm.clone());
            }
            mapping.insert(alias_norm, compare_norm.clone());
        }

        if let Some(display_norm) = display_norm {
            mapping
                .entry(display_norm)
                .or_insert_with(|| compare_norm.clone());
        }
    }

    // Python pops clashes from the mapping (as opposed to warn-and-keep).
    // Actually the Python `_compare_replacer` only warns; `_display_replacer`
    // pops. For Compare we preserve Python's warn-and-keep by NOT popping.
    // The `clashes` tracking is kept for future diagnostics only.
    let _ = clashes; // intentional — compare doesn't pop, we still track.

    Replacer {
        needles: Needles::build(mapping),
    }
}

/// Build the Generic replacer — mirrors Python `_generic_replacer`.
fn build_generic(flags: Normalize, cleanup: Cleanup) -> Replacer {
    let norm = norm_fn(flags, cleanup);
    let mut mapping: HashMap<String, String> = HashMap::new();

    for spec in ORG_TYPE_SPECS.iter() {
        let Some(generic_norm) = spec.generic.as_deref().and_then(&norm) else {
            continue;
        };

        for alias in &spec.aliases {
            let Some(alias_norm) = norm(alias) else {
                continue;
            };
            mapping.insert(alias_norm, generic_norm.clone());
        }

        if let Some(display_norm) = spec.display.as_deref().and_then(&norm) {
            mapping
                .entry(display_norm)
                .or_insert_with(|| generic_norm.clone());
        }
    }

    Replacer {
        needles: Needles::build(mapping),
    }
}

/// Build the Display replacer — mirrors Python `_display_replacer`,
/// which POPS clashes (unlike compare/generic).
///
/// The `flags` parameter governs how the *alias keys* are normalised —
/// they need to match the casefolded haystack built in `replace_display`,
/// so include `CASEFOLD` in flags for Unicode-case-insensitive matching.
/// The display *targets* are normalised with a case-preserving rule
/// (strip + squash_spaces) independent of `flags`, so the output still
/// reads as a proper display form ("AG", "GmbH") rather than a
/// casefolded key ("ag", "gmbh").
fn build_display(flags: Normalize, cleanup: Cleanup) -> Replacer {
    let norm = norm_fn(flags, cleanup);
    let display_target_norm = norm_fn(Normalize::STRIP | Normalize::SQUASH_SPACES, Cleanup::Noop);

    let mut mapping: HashMap<String, String> = HashMap::new();
    let mut seen_targets: HashMap<String, String> = HashMap::new();
    let mut clashes: HashSet<String> = HashSet::new();

    for spec in ORG_TYPE_SPECS.iter() {
        if spec.display.as_deref().and_then(&norm).is_none() {
            continue; // display doesn't survive key normalisation
        }
        let Some(display_target) = spec.display.as_deref().and_then(&display_target_norm) else {
            continue;
        };
        for alias in &spec.aliases {
            let Some(alias_key) = norm(alias) else {
                continue;
            };
            // Trivial identity: skip only when the case-preserving
            // form of the alias equals the display target, i.e. the
            // replacement would reproduce the match verbatim.
            let alias_target = display_target_norm(alias);
            if alias_key.is_empty() || alias_target.as_deref() == Some(display_target.as_str()) {
                continue;
            }
            if let Some(prev) = seen_targets.get(&alias_key) {
                if prev != &display_target {
                    clashes.insert(alias_key.clone());
                }
            } else {
                seen_targets.insert(alias_key.clone(), display_target.clone());
            }
            mapping.insert(alias_key, display_target.clone());
        }
    }

    for key in clashes {
        mapping.remove(&key);
    }

    Replacer {
        needles: Needles::build(mapping),
    }
}

type ReplacerCache = RwLock<HashMap<(ReplacerKind, Normalize, Cleanup), Arc<Replacer>>>;

static REPLACER_CACHE: LazyLock<ReplacerCache> = LazyLock::new(|| RwLock::new(HashMap::new()));

fn get_replacer(kind: ReplacerKind, flags: Normalize, cleanup: Cleanup) -> Arc<Replacer> {
    let key = (kind, flags, cleanup);
    if let Some(existing) = REPLACER_CACHE.read().unwrap().get(&key) {
        return existing.clone();
    }
    let built = Arc::new(match kind {
        ReplacerKind::Compare => build_compare(flags, cleanup),
        ReplacerKind::Display => build_display(flags, cleanup),
        ReplacerKind::Generic => build_generic(flags, cleanup),
    });
    let mut writer = REPLACER_CACHE.write().unwrap();
    Arc::clone(writer.entry(key).or_insert(built))
}

// ----- Public functions -----

/// Replace recognised org types with their compare / generic form.
/// `generic=false` uses the Compare replacer (target = `compare`
/// form, or display if absent, or "" for explicit removal).
/// `generic=true` uses the Generic replacer (target = `generic`
/// form like LLC, JSC; specs without a generic are left alone).
///
/// Assumes `text` has already been normalised with the same flags
/// the alias set was built with — i.e. the caller runs the same
/// `normalize(text, flags, cleanup)` before calling.
pub fn replace_compare(text: &str, flags: Normalize, cleanup: Cleanup, generic: bool) -> String {
    let kind = if generic {
        ReplacerKind::Generic
    } else {
        ReplacerKind::Compare
    };
    get_replacer(kind, flags, cleanup).replace(text)
}

/// The display-path haystack: `text` run through the same
/// normalisation as the needle keys (casefold, whitespace squash,
/// format-char deletion), with a per-byte map back to the byte range
/// of the original character that produced it. Matching happens on
/// `hay`; payloads are spliced into the original text at mapped
/// offsets, so everything outside a match is returned verbatim.
struct MappedHaystack {
    hay: String,
    /// spans[i] = (start, end) byte range in the original text of
    /// the character that produced haystack byte i.
    spans: Vec<(u32, u32)>,
}

impl MappedHaystack {
    /// Supports the flag steps whose offsets can be mapped
    /// char-by-char: CASEFOLD and SQUASH_SPACES (STRIP is subsumed —
    /// edge whitespace simply never matches a trimmed needle).
    /// Unicode normal forms, NAME and category cleanup reorder or
    /// merge characters and are handled by the degraded path in
    /// `replace_display` instead.
    fn supported(flags: Normalize, cleanup: Cleanup) -> bool {
        cleanup == Cleanup::Noop
            && !flags
                .intersects(Normalize::NFC | Normalize::NFKC | Normalize::NFKD | Normalize::NAME)
    }

    fn build(text: &str, flags: Normalize) -> Self {
        let fold = flags.contains(Normalize::CASEFOLD);
        let squash = flags.contains(Normalize::SQUASH_SPACES);
        let mapper = CaseMapper::new();
        let mut hay = String::with_capacity(text.len());
        let mut spans: Vec<(u32, u32)> = Vec::with_capacity(text.len());
        let mut last_was_space = true; // suppresses leading whitespace
        let mut buf = [0u8; 4];
        for (i, ch) in text.char_indices() {
            let span = (i as u32, (i + ch.len_utf8()) as u32);
            if squash {
                match squash_action(ch) {
                    SquashAction::Delete => continue,
                    SquashAction::Space => {
                        if !last_was_space {
                            hay.push(' ');
                            spans.push(span);
                            last_was_space = true;
                        }
                        continue;
                    }
                    SquashAction::Keep => last_was_space = false,
                }
            }
            if fold {
                // Full casefold is context-free (unlike lowercasing,
                // which special-cases e.g. Greek final sigma by
                // position), so folding char-by-char equals folding
                // the whole string — and gives us the offset map.
                let folded = mapper.fold_string(ch.encode_utf8(&mut buf));
                hay.push_str(&folded);
                for _ in 0..folded.len() {
                    spans.push(span);
                }
            } else {
                hay.push(ch);
                for _ in 0..ch.len_utf8() {
                    spans.push(span);
                }
            }
        }
        if squash && hay.ends_with(' ') {
            hay.pop();
            spans.pop();
        }
        Self { hay, spans }
    }
}

/// Replace recognised org types with their short display form
/// (e.g. "Aktiengesellschaft" → "AG"), returning everything outside
/// the matched spans verbatim — case, spacing and stray characters
/// in non-matched regions are untouched. If `text` is all uppercase
/// (Python `str.isupper()` semantics), the whole output is
/// re-uppercased: "ACME COMPANY LIMITED" comes back as
/// "ACME COMPANY LTD", not the odd-looking "ACME COMPANY Ltd".
///
/// Matching is Unicode-case- and whitespace-insensitive: the input
/// is run through the same normalisation as the alias keys (which
/// `flags` must therefore include `Normalize::CASEFOLD` for — the
/// default in `org_types.py` does), and match offsets are mapped
/// back to the original text. Flag steps that can't be offset-mapped
/// (Unicode normal forms, NAME, category cleanup) degrade to
/// matching and splicing on the normalised text itself — correct
/// matches, but the non-matched regions come back normalised rather
/// than verbatim.
pub fn replace_display(text: &str, flags: Normalize, cleanup: Cleanup) -> String {
    let is_upper = python_isupper(text);
    let replacer = get_replacer(ReplacerKind::Display, flags, cleanup);

    if !MappedHaystack::supported(flags, cleanup) {
        let Some(hay) = normalize(text, flags, cleanup) else {
            return text.to_string();
        };
        let out = replacer.replace(&hay);
        return if is_upper { out.to_uppercase() } else { out };
    }

    let mapped = MappedHaystack::build(text, flags);
    let mut out = String::with_capacity(text.len());
    let mut cursor = 0usize; // byte offset into `text`
    for m in replacer.needles.find_iter(&mapped.hay) {
        let orig_start = mapped.spans[m.start].0 as usize;
        let orig_end = mapped.spans[m.end - 1].1 as usize;
        // A match boundary inside one char's fold expansion (ß → ss)
        // can't reach here — the surrounding fold bytes are word
        // chars, so the boundary check already rejected it. Guard
        // anyway rather than risk a backwards slice.
        if orig_start < cursor {
            continue;
        }
        out.push_str(&text[cursor..orig_start]);
        out.push_str(m.payload);
        cursor = orig_end;
    }
    out.push_str(&text[cursor..]);
    if is_upper { out.to_uppercase() } else { out }
}

/// Remove recognised org types by substituting each match with
/// `replacement` (empty string by default, i.e. strip them out).
/// Uses the Compare alias set.
pub fn remove(text: &str, flags: Normalize, cleanup: Cleanup, replacement: &str) -> String {
    get_replacer(ReplacerKind::Compare, flags, cleanup).remove(text, replacement)
}

/// Return every `(matched_text, target)` pair for recognised org
/// types in `text`. `generic` toggles Compare vs Generic replacer.
pub fn extract(
    text: &str,
    flags: Normalize,
    cleanup: Cleanup,
    generic: bool,
) -> Vec<(String, String)> {
    let kind = if generic {
        ReplacerKind::Generic
    } else {
        ReplacerKind::Compare
    };
    get_replacer(kind, flags, cleanup).extract(text)
}

/// Python `str.isupper()`: true iff at least one cased char and all
/// cased chars are uppercase.
fn python_isupper(s: &str) -> bool {
    let mut has_upper = false;
    for c in s.chars() {
        if c.is_lowercase() {
            return false;
        }
        if c.is_uppercase() {
            has_upper = true;
        }
    }
    has_upper
}

#[cfg(test)]
mod tests {
    use super::*;

    const COMPARE_FLAGS: Normalize = Normalize::CASEFOLD.union(Normalize::SQUASH_SPACES);

    #[test]
    fn compare_replaces_common_forms() {
        assert_eq!(
            replace_compare(
                "siemens aktiengesellschaft",
                COMPARE_FLAGS,
                Cleanup::Noop,
                false
            ),
            "siemens ag"
        );
    }

    #[test]
    fn compare_generic_variant() {
        assert_eq!(
            replace_compare("siemens ag", COMPARE_FLAGS, Cleanup::Noop, true),
            "siemens jsc"
        );
    }

    #[test]
    fn extract_returns_matched_and_target() {
        let out = extract(
            "siemens aktiengesellschaft",
            COMPARE_FLAGS,
            Cleanup::Noop,
            false,
        );
        assert_eq!(out, vec![("aktiengesellschaft".into(), "ag".into())]);
    }

    #[test]
    fn remove_strips_with_empty_replacement() {
        assert_eq!(
            remove("siemens gmbh", COMPARE_FLAGS, Cleanup::Noop, "").trim(),
            "siemens"
        );
    }

    #[test]
    fn display_preserves_unmatched_case() {
        assert_eq!(
            replace_display("Siemens Aktiengesellschaft", COMPARE_FLAGS, Cleanup::Noop),
            "Siemens AG"
        );
    }

    #[test]
    fn display_uppercases_if_input_isupper() {
        let long = "SIEMENS GESELLSCHAFT MIT BESCHRÄNKTER HAFTUNG";
        assert_eq!(
            replace_display(long, COMPARE_FLAGS, Cleanup::Noop),
            "SIEMENS GMBH"
        );
    }

    #[test]
    fn display_no_panic_on_byte_shifting_lowercase() {
        // KELVIN SIGN (U+212A, 3 bytes) lowercases to 'k' (1 byte)
        // and U+023A (2 bytes) to U+2C65 (3 bytes) — the old total-
        // byte-length parity check passed while per-char offsets were
        // misaligned, slicing mid-char and panicking.
        assert_eq!(
            replace_display("\u{212A} gmbh \u{23A}\u{23A}", COMPARE_FLAGS, Cleanup::Noop),
            "\u{212A} GmbH \u{23A}\u{23A}"
        );
    }

    #[test]
    fn display_matches_greek_final_sigma() {
        // The alias contains word-final 'ς'; casefold maps it to 'σ'
        // in the needle keys. The haystack must be casefolded the
        // same way (to_lowercase preserves 'ς' and never matches).
        assert_eq!(
            replace_display(
                "Acme Εταιρία Περιορισμένης Ευθύνης",
                COMPARE_FLAGS,
                Cleanup::Noop
            ),
            "Acme Ε.Π.Ε."
        );
    }

    #[test]
    fn display_canonicalises_case_variants() {
        // "GMBH" is a shipped alias of display "GmbH" — a case
        // variant, not a trivial identity. The identity-skip must
        // compare case-preserving forms or these aliases are dropped.
        assert_eq!(
            replace_display("Siemens GMBH", COMPARE_FLAGS, Cleanup::Noop),
            "Siemens GmbH"
        );
        // ... but ALL-CAPS input stays ALL-CAPS via the isupper hook.
        assert_eq!(
            replace_display("SIEMENS GMBH", COMPARE_FLAGS, Cleanup::Noop),
            "SIEMENS GMBH"
        );
    }

    #[test]
    fn display_matches_through_format_chars_and_extra_spaces() {
        // Soft hyphen inside the alias (PDF copy/paste residue) and a
        // doubled space inside a spelt-out form: the haystack is
        // squashed like the needle keys, so both match; the replaced
        // span swallows the junk.
        assert_eq!(
            replace_display("Acme Gm\u{AD}bH", COMPARE_FLAGS, Cleanup::Noop),
            "Acme GmbH"
        );
        assert_eq!(
            replace_display(
                "Siemens Gesellschaft  mit beschränkter Haftung",
                COMPARE_FLAGS,
                Cleanup::Noop
            ),
            "Siemens GmbH"
        );
    }

    #[test]
    fn display_preserves_unmatched_regions_verbatim() {
        // Junk outside the matched span — doubled spaces, soft
        // hyphens — is returned untouched.
        assert_eq!(
            replace_display(
                "Acme  Hol\u{AD}dings Aktiengesellschaft",
                COMPARE_FLAGS,
                Cleanup::Noop
            ),
            "Acme  Hol\u{AD}dings AG"
        );
    }

    #[test]
    fn display_offsets_survive_fold_expansion() {
        // 'ß' casefolds to "ss", shifting every haystack offset after
        // it by one byte; the match must still splice at the right
        // place in the original.
        assert_eq!(
            replace_display(
                "Meißner Straßenbau Aktiengesellschaft",
                COMPARE_FLAGS,
                Cleanup::Noop
            ),
            "Meißner Straßenbau AG"
        );
    }

    #[test]
    fn display_degraded_path_for_unmappable_flags() {
        // NFKD can't be offset-mapped; the degraded path matches and
        // splices on the normalised text (still no panic, still
        // replaces) instead of returning verbatim surroundings.
        let flags = COMPARE_FLAGS.union(Normalize::NFKD);
        let out = replace_display("Siemens Aktiengesellschaft", flags, Cleanup::Noop);
        assert_eq!(out, "siemens AG");
    }

    #[test]
    fn cache_keys_include_kind() {
        let compare = get_replacer(ReplacerKind::Compare, COMPARE_FLAGS, Cleanup::Noop);
        let display = get_replacer(ReplacerKind::Display, COMPARE_FLAGS, Cleanup::Noop);
        let generic = get_replacer(ReplacerKind::Generic, COMPARE_FLAGS, Cleanup::Noop);
        assert!(!Arc::ptr_eq(&compare, &display));
        assert!(!Arc::ptr_eq(&compare, &generic));
        assert!(!Arc::ptr_eq(&display, &generic));
    }
}
