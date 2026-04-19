// Rust port of `rigour.names.org_types.*`.
//
// Loads rust/data/org_types.json (generated from
// resources/names/org_types.yml by genscripts/generate_names.py) and
// exposes the four public org-type functions: replace_compare,
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
//   skips aliases that equal their display form (trivial identity),
//   pops on clash. Display-form is NOT added as a lookup (matching
//   Python's `_display_replacer`).
//
// ## Flag-keyed cache
//
// Each `(ReplacerKind, Normalize, Cleanup)` combination yields one
// compiled Replacer. First access pays the build cost; subsequent
// calls hit the cache. Same lifecycle as Python's `@cache`-decorated
// replacers.

use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, LazyLock, RwLock};

use crate::names::matcher::Needles;
use crate::text::normalize::{Cleanup, Normalize, normalize};

#[derive(Debug, Deserialize)]
struct OrgTypeSpec {
    #[serde(default)]
    display: Option<String>,
    #[serde(default)]
    compare: Option<String>,
    #[serde(default)]
    generic: Option<String>,
    #[serde(default)]
    aliases: Vec<String>,
}

const ORG_TYPES_JSON: &str = include_str!("../../data/org_types.json");

static ORG_TYPE_SPECS: LazyLock<Vec<OrgTypeSpec>> = LazyLock::new(|| {
    serde_json::from_str(ORG_TYPES_JSON).expect("org_types.json parses")
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
    let display_target_norm =
        norm_fn(Normalize::STRIP | Normalize::SQUASH_SPACES, Cleanup::Noop);

    let mut mapping: HashMap<String, String> = HashMap::new();
    let mut seen_targets: HashMap<String, String> = HashMap::new();
    let mut clashes: HashSet<String> = HashSet::new();

    for spec in ORG_TYPE_SPECS.iter() {
        let Some(display_key) = spec.display.as_deref().and_then(&norm) else {
            continue;
        };
        let Some(display_target) = spec.display.as_deref().and_then(&display_target_norm) else {
            continue;
        };
        for alias in &spec.aliases {
            let Some(alias_key) = norm(alias) else {
                continue;
            };
            if alias_key.is_empty() || alias_key == display_key {
                continue; // trivial identity, skip
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

static REPLACER_CACHE: LazyLock<ReplacerCache> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

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

/// Replace recognised org types with their short display form
/// (e.g. "Aktiengesellschaft" → "AG"). Matches case-insensitively
/// across Unicode by casefolding a copy of `text` for the match —
/// non-matched regions are emitted from `text` so their case is
/// preserved. If `text` is all uppercase, the whole output is
/// re-uppercased (mirrors Python's `isupper()` hook).
///
/// Flags must include `Normalize::CASEFOLD` for aliases to be
/// casefolded at build time — that's what enables Unicode case-
/// insensitive matching. The default in `org_types.py` does this.
///
/// Byte-position parity between `text` and its casefolded copy is
/// assumed for position mapping. This holds for ASCII, Cyrillic,
/// Greek, and CJK — it fails only for rare chars like `ẞ → ss`,
/// which don't appear in realistic org-type inputs.
pub fn replace_display(text: &str, flags: Normalize, cleanup: Cleanup) -> String {
    let is_upper = python_isupper(text);
    let replacer = get_replacer(ReplacerKind::Display, flags, cleanup);

    // Casefold a copy of text so the AC can match Unicode-case-
    // insensitively (the aliases in Needles were casefolded at build
    // time via `flags | CASEFOLD`). If byte lengths diverge, fall back
    // to matching on text directly — AC's ASCII-only case insensitivity
    // still handles most inputs.
    let haystack = text.to_lowercase();
    let use_cf = haystack.len() == text.len();
    let matcher_input = if use_cf { haystack.as_str() } else { text };

    let mut out = String::with_capacity(text.len());
    let mut cursor = 0;
    for m in replacer.needles.find_iter(matcher_input) {
        // Slice original text at matcher-input positions. Byte-parity
        // between text and matcher_input is guaranteed here (either
        // matcher_input IS text, or we verified same length above).
        out.push_str(&text[cursor..m.start]);
        out.push_str(m.payload);
        cursor = m.end;
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
            replace_compare("siemens aktiengesellschaft", COMPARE_FLAGS, Cleanup::Noop, false),
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
    fn cache_keys_include_kind() {
        let compare = get_replacer(ReplacerKind::Compare, COMPARE_FLAGS, Cleanup::Noop);
        let display = get_replacer(ReplacerKind::Display, COMPARE_FLAGS, Cleanup::Noop);
        let generic = get_replacer(ReplacerKind::Generic, COMPARE_FLAGS, Cleanup::Noop);
        assert!(!Arc::ptr_eq(&compare, &display));
        assert!(!Arc::ptr_eq(&compare, &generic));
        assert!(!Arc::ptr_eq(&display, &generic));
    }
}
