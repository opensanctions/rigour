// AC-based name tagger — the Rust side of
// `rigour.names.tagging.tag_{org,person}_name`.
//
// Consumes every Rust-owned tagger data source at build time:
//
//   - `text/ordinals.json`      → NUMERIC symbols (both taggers)
//   - `names/symbols.json`      → SYMBOL / DOMAIN / NAME / NICK symbols
//   - `territories/data.jsonl`  → LOCATION symbols (org only)
//   - `org_types.json`          → ORG_CLASS symbols (org only, from generic field)
//   - `names/person_names.txt`  → NAME symbols with Wikidata/X-prefixed ids
//                                 (person only, via names::person_names)
//
// Each source contributes to a `HashMap<String, Vec<Symbol>>` that
// seeds `Needles<Vec<Symbol>>`. Aliases are normalised with the
// caller's `(Normalize, Cleanup)` flags before insertion — callers
// must normalise runtime input with the same flags. Python callers
// use `tag_{org,person}_matches` over FFI; match results flow back
// as `(matched_phrase, Symbol)` pairs and the Python `tag_*_name`
// wrappers apply each via `Name.apply_phrase`.
//
// Flag-keyed cache: one compiled Tagger per `(TaggerKind, Normalize,
// Cleanup)` combination, same shape as the org_types Replacer cache.

use std::collections::HashMap;
use std::sync::{Arc, LazyLock, RwLock};

use serde::Deserialize;

use crate::names::matcher::Needles;
use crate::names::org_types;
use crate::names::person_names;
use crate::names::symbol::{Symbol, SymbolCategory};
use crate::names::symbols as name_symbols;
use crate::territories;
use crate::text::normalize::{Cleanup, Normalize, normalize};
use crate::text::ordinals;
use crate::text::tokenize::tokenize_name;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum TaggerKind {
    Org,
    Person,
}

pub struct Tagger {
    needles: Needles<Vec<Symbol>>,
}

impl Tagger {
    /// Match pre-normalised `text` against the tagger's alias set.
    /// One `(phrase, symbol)` pair per match × symbol in the
    /// payload — matches today's Python `Tagger.__call__` output
    /// shape that `tag_*_name` consumes.
    pub fn tag(&self, text: &str) -> Vec<(String, Symbol)> {
        // Use overlapping iteration — the tagger wants every
        // recognised phrase as an independent match, not a
        // non-overlapping greedy selection. Same semantic as today's
        // Python tagger calling `ahocorasick-rs` with overlapping=True.
        let mut out: Vec<(String, Symbol)> = Vec::new();
        for m in self.needles.find_overlapping(text) {
            for sym in m.payload {
                out.push((m.matched.to_string(), sym.clone()));
            }
        }
        out
    }
}

/// Builder state — accumulate phrase → symbols entries as we walk
/// every data source, dedup-friendly via Vec append.
struct Builder {
    flags: Normalize,
    mapping: HashMap<String, Vec<Symbol>>,
}

impl Builder {
    fn new(flags: Normalize) -> Self {
        Self {
            flags,
            mapping: HashMap::new(),
        }
    }

    fn norm(&self, s: &str) -> Option<String> {
        // Mirror the Python haystack pipeline:
        //
        //   Name.norm_form = " ".join(part.form for part in parts)
        //                  = " ".join(tokenize_name(casefold(original)))
        //
        // So aliases get normalised with the same shape:
        //   1. caller's flags (for casefold and any Unicode-normalisation bits)
        //      minus SQUASH_SPACES — the tokens-joined-by-ASCII-space shape
        //      below makes squashing redundant.
        //   2. tokenize_name() → tokens → join with ASCII space.
        //
        // No Cleanup is applied — tokenize_name subsumes its role
        // (Unicode-category handling + skip-char deletion) and the
        // runtime haystack never goes through `Cleanup::Strong` either.
        // Applying it here would drop chars the haystack keeps (CJK
        // Lm, Mc), breaking matches.
        let pre_flags = self.flags - Normalize::SQUASH_SPACES;
        let pre = normalize(s, pre_flags, Cleanup::Noop)?;
        let tokens = tokenize_name(&pre, 1);
        if tokens.is_empty() {
            return None;
        }
        Some(tokens.join(" "))
    }

    fn add(&mut self, alias: &str, symbol: &Symbol) {
        let Some(key) = self.norm(alias) else {
            return;
        };
        if key.is_empty() {
            return;
        }
        let entry = self.mapping.entry(key).or_default();
        // Linear dedupe within the per-phrase Vec — at our sizes
        // (usually 1–3 Symbols per phrase) this beats a HashSet.
        if !entry.iter().any(|s| s == symbol) {
            entry.push(symbol.clone());
        }
    }

    fn finish(self) -> Tagger {
        Tagger {
            needles: Needles::build(self.mapping),
        }
    }
}

/// Fields from the territory JSONL that the tagger actually reads —
/// everything else is consumed by `rigour.territories.*` on the
/// Python side and ignored here.
#[derive(Debug, Deserialize)]
struct TerritoryRecord {
    code: String,
    name: String,
    full_name: Option<String>,
    #[serde(default)]
    names_strong: Vec<String>,
}

fn add_common_symbols(b: &mut Builder) {
    // Ordinals: NUMERIC id is the integer directly (stringified via
    // Symbol::from_u32).
    for spec in ordinals::ordinals() {
        let sym = Symbol::from_u32(SymbolCategory::NUMERIC, spec.number);
        for form in &spec.forms {
            b.add(form, &sym);
        }
    }
}

fn build_org_tagger(flags: Normalize) -> Tagger {
    let mut b = Builder::new(flags);
    add_common_symbols(&mut b);

    let syms = name_symbols::data();

    for (key, aliases) in &syms.org_symbols {
        let sym = Symbol::from_str(SymbolCategory::SYMBOL, &key.to_uppercase());
        for alias in aliases {
            b.add(alias, &sym);
        }
    }

    for (key, aliases) in &syms.org_domains {
        let sym = Symbol::from_str(SymbolCategory::DOMAIN, &key.to_uppercase());
        for alias in aliases {
            b.add(alias, &sym);
        }
    }

    // Territories → LOCATION symbols. Walk the JSONL line by line;
    // serde parses only the tagger-relevant fields.
    for line in territories::raw().lines() {
        if line.is_empty() {
            continue;
        }
        let record: TerritoryRecord = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(_) => continue, // skip malformed lines defensively
        };
        let sym = Symbol::from_str(SymbolCategory::LOCATION, &record.code);
        b.add(&record.name, &sym);
        if let Some(full) = &record.full_name {
            b.add(full, &sym);
        }
        for name in &record.names_strong {
            b.add(name, &sym);
        }
    }

    // Org types → ORG_CLASS symbols keyed on the `generic` field.
    // Mirrors the Python tagger's loop at tagging.py:123-145.
    let mut class_syms: HashMap<String, Symbol> = HashMap::new();
    for spec in org_types::ORG_TYPE_SPECS.iter() {
        let Some(generic) = spec.generic.as_deref() else {
            continue;
        };
        let sym = class_syms
            .entry(generic.to_string())
            .or_insert_with(|| Symbol::from_str(SymbolCategory::ORG_CLASS, generic))
            .clone();

        if let Some(display) = spec.display.as_deref() {
            b.add(display, &sym);
        }
        // compare defaults to display when absent; when present but
        // empty ("" = removal marker for the Replacer) it's not an
        // alias we want in the tagger — skip.
        let compare = spec.compare.as_deref().or(spec.display.as_deref());
        match spec.compare.as_deref() {
            Some("") => {}
            Some(s) => b.add(s, &sym),
            None => {
                if let Some(c) = compare {
                    b.add(c, &sym);
                }
            }
        }
        // Python's Python tagger adds aliases only when compare is
        // absent — mirror that exactly.
        if spec.compare.is_none() {
            for alias in &spec.aliases {
                b.add(alias, &sym);
            }
        }
    }

    b.finish()
}

fn build_person_tagger(flags: Normalize) -> Tagger {
    let mut b = Builder::new(flags);
    add_common_symbols(&mut b);

    let syms = name_symbols::data();

    for (key, aliases) in &syms.person_symbols {
        let sym = Symbol::from_str(SymbolCategory::SYMBOL, &key.to_uppercase());
        for alias in aliases {
            b.add(alias, &sym);
        }
    }

    for (key, aliases) in &syms.person_name_parts {
        let sym = Symbol::from_str(SymbolCategory::NAME, &key.to_uppercase());
        for alias in aliases {
            b.add(alias, &sym);
        }
    }

    for (key, aliases) in &syms.person_nick {
        let sym = Symbol::from_str(SymbolCategory::NICK, &key.to_uppercase());
        for alias in aliases {
            b.add(alias, &sym);
        }
    }

    // Person-names corpus: one record per line, "alias1, alias2, ... => gid".
    // gid is a Wikidata QID ("Qxxxx") or an X-prefixed manual override.
    // Stored verbatim as the Symbol id (Symbol uses Arc<str>, so
    // distinct ids stay distinct even when prefixes collide with
    // integer values of other categories).
    //
    // Python parity: skip records with <2 distinct normalised aliases —
    // a mapping of one form to itself adds no matching power. Matches
    // tagging.py:234.
    for line in person_names::raw().lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Some((forms_raw, gid)) = line.rsplit_once(" => ") else {
            continue;
        };
        let sym = Symbol::from_str(SymbolCategory::NAME, gid);

        let mut normed: std::collections::HashSet<String> = std::collections::HashSet::new();
        for alias in forms_raw.split(", ") {
            if let Some(k) = b.norm(alias) {
                if !k.is_empty() {
                    normed.insert(k);
                }
            }
        }
        if normed.len() < 2 {
            continue;
        }
        for form in normed {
            let entry = b.mapping.entry(form).or_default();
            if !entry.iter().any(|s| s == &sym) {
                entry.push(sym.clone());
            }
        }
    }

    b.finish()
}

type TaggerCache = RwLock<HashMap<(TaggerKind, Normalize), Arc<Tagger>>>;

static TAGGER_CACHE: LazyLock<TaggerCache> = LazyLock::new(|| RwLock::new(HashMap::new()));

pub fn get_tagger(kind: TaggerKind, flags: Normalize) -> Arc<Tagger> {
    let key = (kind, flags);
    if let Some(existing) = TAGGER_CACHE.read().unwrap().get(&key) {
        return existing.clone();
    }
    let built = Arc::new(match kind {
        TaggerKind::Org => build_org_tagger(flags),
        TaggerKind::Person => build_person_tagger(flags),
    });
    let mut writer = TAGGER_CACHE.write().unwrap();
    Arc::clone(writer.entry(key).or_insert(built))
}

#[cfg(test)]
mod tests {
    use super::*;

    // Matches the default pinned on the Python wrapper.
    const FLAGS: Normalize = Normalize::CASEFOLD.union(Normalize::SQUASH_SPACES);

    #[test]
    fn org_tagger_matches_ordinals() {
        let tagger = get_tagger(TaggerKind::Org, FLAGS);
        let matches = tagger.tag("acme number one limited");
        assert!(
            matches
                .iter()
                .any(|(_, s)| s.category == SymbolCategory::NUMERIC),
            "expected a NUMERIC match, got {:?}",
            matches
        );
    }

    #[test]
    fn org_tagger_matches_org_class() {
        let tagger = get_tagger(TaggerKind::Org, FLAGS);
        // "aktiengesellschaft" should map to ORG_CLASS (via generic=JSC).
        let matches = tagger.tag("siemens aktiengesellschaft");
        assert!(
            matches
                .iter()
                .any(|(_, s)| s.category == SymbolCategory::ORG_CLASS),
            "expected ORG_CLASS match in: {:?}",
            matches
        );
    }

    #[test]
    fn person_tagger_matches_corpus_name() {
        let tagger = get_tagger(TaggerKind::Person, FLAGS);
        // Any name from the corpus should produce at least one NAME
        // symbol. Pick "john" — extremely common, should resolve to
        // at least one Wikidata-keyed Symbol.
        let matches = tagger.tag("john smith");
        assert!(
            matches
                .iter()
                .any(|(_, s)| s.category == SymbolCategory::NAME),
            "expected a NAME symbol for 'john smith', got {:?}",
            matches
        );
    }

    #[test]
    fn cache_returns_same_arc() {
        let a = get_tagger(TaggerKind::Org, FLAGS);
        let b = get_tagger(TaggerKind::Org, FLAGS);
        assert!(Arc::ptr_eq(&a, &b));
    }

    #[test]
    fn cache_distinguishes_kind() {
        let org = get_tagger(TaggerKind::Org, FLAGS);
        let person = get_tagger(TaggerKind::Person, FLAGS);
        assert!(!Arc::ptr_eq(&org, &person));
    }
}
