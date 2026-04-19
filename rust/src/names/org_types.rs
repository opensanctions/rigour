// Rust port of `rigour.names.org_types.replace_org_types_compare`.
//
// Loads rust/data/org_types.json (generated from
// resources/names/org_types.yml by genscripts/generate_names.py),
// builds a case-insensitive literal-string matcher keyed on alias
// forms normalised with caller-supplied Normalize flags, and exposes
// `replace_org_types_compare` via PyO3. The Python side
// (rigour/names/org_types_rust.py) wraps the _core call so benchmarks
// and parity tests can pit Python and Rust against each other.
//
// Matching uses the shared `names::matcher::Needles<T>` substrate
// (Aho-Corasick + Python-style `(?<!\w)X(?!\w)` boundary check). Same
// substrate will back the symbol tagger in a follow-up. See
// `matcher.rs` for the find-overlapping + greedy-select algorithm
// and the rationale for why regex crates were wrong for this shape.
//
// ## Flag-keyed cache
//
// The normaliser applied to alias forms at build time is a caller
// choice, expressed as `Normalize` flags (plus `Cleanup`). Each
// distinct flag combination yields a different set of normalised
// aliases and therefore a different built automaton. We cache
// Replacers keyed on `(Normalize, Cleanup)` — same lifecycle as
// Python's `@cache`-decorated `_compare_replacer(normalizer=…)`.
// Empirically there are 1–2 distinct flag sets in use across the
// rigour / FTM / nomenklatura / yente stack.

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
    // `generic` is deserialised for schema fidelity with the Python
    // OrgTypeSpec dict but not consumed by the compare replacer — it
    // feeds a separate `_generic_replacer` path in Python that we
    // haven't ported yet.
    #[serde(default)]
    #[allow(dead_code)]
    generic: Option<String>,
    #[serde(default)]
    aliases: Vec<String>,
}

const ORG_TYPES_JSON: &str = include_str!("../../data/org_types.json");

static ORG_TYPE_SPECS: LazyLock<Vec<OrgTypeSpec>> = LazyLock::new(|| {
    serde_json::from_str(ORG_TYPES_JSON).expect("org_types.json parses")
});

/// An org-type replacer built from a specific `(Normalize, Cleanup)`
/// flag combo. Wraps the generic `Needles<String>` substrate with
/// payloads set to each alias's compare-form target.
pub struct Replacer {
    needles: Needles<String>,
}

impl Replacer {
    /// Apply the replacer on pre-normalised text. Returns a new
    /// String with every matched alias substituted for its
    /// compare-form target.
    pub fn replace(&self, text: &str) -> String {
        let mut out = String::with_capacity(text.len());
        let mut cursor = 0;
        for m in self.needles.find_iter(text) {
            out.push_str(&text[cursor..m.start]);
            out.push_str(m.payload);
            cursor = m.end;
        }
        out.push_str(&text[cursor..]);
        out
    }
}

fn build_compare_replacer(flags: Normalize, cleanup: Cleanup) -> Replacer {
    let norm = |text: &str| normalize(text, flags, cleanup);
    let mut mapping: HashMap<String, String> = HashMap::new();
    // Track clash sites so we can drop ambiguous aliases — matches
    // the Python `_compare_replacer` path.
    let mut seen_targets: HashMap<String, String> = HashMap::new();
    let mut clashes: HashSet<String> = HashSet::new();

    for spec in ORG_TYPE_SPECS.iter() {
        let display_norm = spec.display.as_deref().and_then(&norm);
        // `compare` is an explicit alternate target — if absent, fall
        // back to `display`. Empty-string compare ("") means "remove
        // this org type" (substitute with empty), matching Python.
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

    // Drop any alias that resolves to conflicting targets — matches
    // the Python path, which pops clashes from the mapping.
    for key in clashes {
        mapping.remove(&key);
    }

    let needles = Needles::build(mapping);
    Replacer { needles }
}

type ReplacerCache = RwLock<HashMap<(Normalize, Cleanup), Arc<Replacer>>>;

/// Cache of compiled Replacers, one per `(Normalize, Cleanup)` combo.
/// First call with a given combo pays the build cost; subsequent
/// calls hit the cache.
static REPLACER_CACHE: LazyLock<ReplacerCache> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

fn get_compare_replacer(flags: Normalize, cleanup: Cleanup) -> Arc<Replacer> {
    let key = (flags, cleanup);
    if let Some(existing) = REPLACER_CACHE.read().unwrap().get(&key) {
        return existing.clone();
    }
    // Build with NO lock held, then upgrade to write-lock to insert.
    // Two threads racing on the same key both build; only one wins
    // the insert, the other drops its work. Cheap — the race window
    // is "automaton-build time" and that only happens once per flag
    // combo per process.
    let built = Arc::new(build_compare_replacer(flags, cleanup));
    let mut writer = REPLACER_CACHE.write().unwrap();
    Arc::clone(writer.entry(key).or_insert(built))
}

/// Replace organisation types in `text` with their compare-form
/// targets. `flags` (+ `cleanup`) selects which compiled automaton
/// to use — they determine how the alias list was normalised at
/// build time. Assumes `text` has already been normalised with the
/// same flags by the caller, matching the Python contract.
///
/// Mirrors Python's `replacer(name) or name` fallback: if the full
/// replacement yields an empty string (because the input consisted
/// entirely of aliases that map to compare="" removal targets), the
/// original input is returned unchanged.
pub fn replace_org_types_compare(text: &str, flags: Normalize, cleanup: Cleanup) -> String {
    let replacer = get_compare_replacer(flags, cleanup);
    let replaced = replacer.replace(text);
    if replaced.is_empty() && !text.is_empty() {
        text.to_string()
    } else {
        replaced
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const DEFAULT_FLAGS: Normalize = Normalize::CASEFOLD.union(Normalize::SQUASH_SPACES);

    fn call(text: &str) -> String {
        replace_org_types_compare(text, DEFAULT_FLAGS, Cleanup::Noop)
    }

    #[test]
    fn replaces_common_forms() {
        let out = call("siemens aktiengesellschaft");
        assert!(
            out != "siemens aktiengesellschaft",
            "expected replacement, got: {out}"
        );
    }

    #[test]
    fn passthrough_when_no_match() {
        let input = "just a person's name";
        assert_eq!(call(input), input);
    }

    #[test]
    fn respects_word_boundaries() {
        let input = "bellcorp holdings";
        assert_eq!(call(input), input);
    }

    #[test]
    fn matches_punctuation_terminated_aliases() {
        assert_eq!(call("apple inc."), "apple inc");
    }

    #[test]
    fn rejects_match_followed_by_word_char() {
        assert_eq!(call("apple inc.x"), "apple inc.x");
    }

    #[test]
    fn cache_returns_same_arc_for_repeat_call() {
        let a = get_compare_replacer(DEFAULT_FLAGS, Cleanup::Noop);
        let b = get_compare_replacer(DEFAULT_FLAGS, Cleanup::Noop);
        assert!(Arc::ptr_eq(&a, &b), "cache should return same Arc");
    }

    #[test]
    fn cache_distinguishes_flag_sets() {
        let a = get_compare_replacer(Normalize::CASEFOLD, Cleanup::Noop);
        let b = get_compare_replacer(DEFAULT_FLAGS, Cleanup::Noop);
        assert!(
            !Arc::ptr_eq(&a, &b),
            "different flags should yield different Replacers"
        );
    }
}
