// Single-FFI name-analysis orchestrator. Runs the full name
// pipeline (prefix strip → casefold → org-type rewrite → tagger →
// infer) in one function call with no Python callbacks between
// the steps.
//
// Pipeline per input string:
//   1. For PER, if `rewrite`: remove_person_prefixes
//   2. casefold → form
//   3. For ORG/ENT, if `rewrite`: replace_org_types_compare +
//      remove_org_prefixes
//   4. Dedup by form
//   5. Construct Name + NamePart objects (all eager on construction)
//   6. Apply part_tags via Name.tag_text for each (tag, values) entry
//   7. For PER: INITIAL-symbol preamble (if `symbols`)
//   8. Tagger match → apply_phrase per (phrase, symbol) (if `symbols`)
//   9. infer_part_tags post-pass (NUMERIC / STOP / LEGAL promotion,
//      ENT → ORG upgrade)
// Optionally:
//   10. Name::consolidate_names to drop substring-dominated names
//
// The `rewrite` flag gates the two pre-tagger canonicalisation
// stages. Callers that want to index or display a name in its
// literal form — no honorific strip, no "Inc. → LLC" substitution —
// pass `rewrite=False`. The tagger still fires on the raw tokens
// (its alias set covers both the original and canonical forms).

use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

use pyo3::prelude::*;
use pyo3::types::PySet;

use crate::names::name::Name;
use crate::names::org_types;
use crate::names::part::{NamePart, Span};
use crate::names::prefix::{remove_org_prefixes, remove_person_prefixes};
use crate::names::symbol::{Symbol, SymbolCategory};
use crate::names::tag::{INITIAL_TAGS, NamePartTag, NameTypeTag};
use crate::names::tagger::{TaggerKind, get_tagger};
use crate::text::normalize::{Cleanup, Normalize, casefold, normalize};
use crate::text::stopwords::stopwords_list;

/// Normalise-flag combination for the tagger's alias set.
///
/// Must match the shape of `Name.norm_form` on the haystack side
/// so the AC automaton's needles line up with the text it's
/// searching. `NAME` runs `tokenize_name + ' '.join` as the final
/// pipeline step — this subsumes `SQUASH_SPACES` and the
/// Unicode-category handling + skip-char deletion the pre-port
/// tagger used to do in a hardcoded post-pass.
///
/// No `Cleanup` accepted: `tokenize_name` already handles Unicode
/// categories, and `Cleanup::Strong` would drop Lm/Mc characters
/// (CJK / combining marks) the haystack keeps, breaking matches
/// on non-Latin scripts.
const TAGGER_FLAGS: Normalize = Normalize::CASEFOLD.union(Normalize::NAME);

/// Stopword set, keyed on `normalize_name`-shaped strings. Used by
/// the STOP-tag promotion in `infer_part_tags`. The set is built once
/// per process — stopwords are a small fixed list (~few hundred).
static STOPWORD_SET: LazyLock<HashSet<String>> = LazyLock::new(|| {
    let flags = Normalize::CASEFOLD | Normalize::NAME;
    stopwords_list()
        .into_iter()
        .filter_map(|w| normalize(&w, flags, Cleanup::Noop))
        .collect()
});

fn is_stopword(form: &str) -> bool {
    STOPWORD_SET.contains(form)
}

/// Public entry point — called from PyO3 `py_analyze_names`. See the
/// Python-side docstring at `rigour/names/analyze.py::analyze_names`
/// for the semantic spec.
#[allow(clippy::too_many_arguments)]
pub fn analyze_names(
    py: Python<'_>,
    type_tag: NameTypeTag,
    names: Vec<String>,
    part_tags: HashMap<NamePartTag, Vec<String>>,
    infer_initials: bool,
    symbols: bool,
    phonetics: bool,
    numerics: bool,
    consolidate: bool,
    rewrite: bool,
) -> PyResult<Py<PySet>> {
    let mut seen: HashSet<String> = HashSet::new();
    let mut built: Vec<Py<Name>> = Vec::with_capacity(names.len());

    for raw in names {
        let working = if rewrite && matches!(type_tag, NameTypeTag::PER) {
            remove_person_prefixes(&raw)
        } else {
            raw.clone()
        };
        let mut form = casefold(&working);
        if rewrite && matches!(type_tag, NameTypeTag::ORG | NameTypeTag::ENT) {
            form = org_types::replace_compare(&form, Normalize::CASEFOLD, Cleanup::Noop, false);
            form = remove_org_prefixes(&form);
        }
        if form.is_empty() || seen.contains(&form) {
            continue;
        }
        seen.insert(form.clone());

        // Construct Name (which tokenises internally). `working` is
        // the post-prefix-strip raw; Name's `original` remembers it.
        let name_obj = Name::new(py, &working, Some(&form), type_tag, phonetics)?;
        let name_py = Py::new(py, name_obj)?;

        // Apply part_tags — each value is prenormalised then fed to
        // Name.tag_text, which tokenises + walks parts.
        for (tag, values) in &part_tags {
            for value in values {
                let folded = casefold(value);
                name_py.bind(py).borrow().tag_text(py, &folded, *tag, 1)?;
            }
        }

        if symbols {
            match type_tag {
                NameTypeTag::PER => {
                    apply_initial_preamble(py, &name_py, infer_initials)?;
                    apply_tagger(py, &name_py, TaggerKind::Person)?;
                }
                NameTypeTag::ORG | NameTypeTag::ENT => {
                    apply_tagger(py, &name_py, TaggerKind::Org)?;
                }
                NameTypeTag::OBJ | NameTypeTag::UNK => {
                    // No tagger pass — Name just wraps raw + form + parts.
                }
            }
        }

        infer_part_tags(py, &name_py, symbols, numerics)?;
        built.push(name_py);
    }

    if consolidate {
        consolidate_names(py, built)
    } else {
        let out = PySet::empty(py)?;
        for n in &built {
            out.add(n.clone_ref(py))?;
        }
        Ok(out.unbind())
    }
}

/// INITIAL-symbol pre-pass for PER names. Attaches `INITIAL:<char>`
/// to single-character latin parts (when `infer_initials`) or to
/// parts already tagged with one of [`INITIAL_TAGS`] (GIVEN,
/// MIDDLE, PATRONYMIC, MATRONYMIC). Runs before the AC tagger so
/// INITIAL symbols are visible to downstream matchers that
/// compare against spelled-out given names.
fn apply_initial_preamble(py: Python<'_>, name: &Py<Name>, infer_initials: bool) -> PyResult<()> {
    let parts_list = name.bind(py).borrow().parts.clone_ref(py);
    for item in parts_list.bind(py).iter() {
        let part_py = item.cast::<NamePart>()?;
        let part = part_py.borrow();
        if !part.latinize {
            continue;
        }
        let Some(first_char) = part.comparable_str().chars().next() else {
            continue;
        };
        let sym_id = first_char.to_string();
        let sym = Symbol::from_str(SymbolCategory::INITIAL, &sym_id);
        let sym_py = Py::new(py, sym)?;

        let form_str = part.form_str().to_string();
        let tag = part.tag;
        drop(part);

        let apply = if infer_initials && form_str.chars().count() == 1 {
            true
        } else {
            INITIAL_TAGS.contains(&tag)
        };
        if apply {
            let part_ref = part_py.clone().unbind();
            name.bind(py).borrow().apply_part(py, part_ref, sym_py)?;
        }
    }
    Ok(())
}

/// Run the AC tagger for `kind`, applying every (phrase, symbol) match
/// to `name` via `apply_phrase`.
fn apply_tagger(py: Python<'_>, name: &Py<Name>, kind: TaggerKind) -> PyResult<()> {
    let norm_form: String = name.bind(py).borrow().norm_form.bind(py).extract()?;
    let tagger = get_tagger(kind, TAGGER_FLAGS);
    let matches = tagger.tag(&norm_form);
    for (phrase, symbol) in matches {
        let sym_py = Py::new(py, symbol)?;
        name.bind(py).borrow().apply_phrase(py, &phrase, sym_py)?;
    }
    Ok(())
}

/// Post-tagger inference pass. Walks the spans produced by the
/// tagger to promote UNSET parts based on collected evidence:
///
/// * Parts inside an ORG_CLASS span become `NamePartTag::LEGAL`;
///   a long enough ORG_CLASS span upgrades the Name's tag from
///   ENT to ORG.
/// * Numeric-looking UNSET parts become `NamePartTag::NUM` and —
///   when `numerics` is true — gain a `NUMERIC` symbol if the
///   ordinal tagger didn't already cover them.
/// * UNSET parts that are stopwords become `NamePartTag::STOP`.
///
/// `symbols` gates NUMERIC-symbol emission: when `false`, NUM /
/// STOP / LEGAL part-tag promotions still fire but no new Symbol
/// is attached. Mutates the Name and its NamePart tags in place.
fn infer_part_tags(py: Python<'_>, name: &Py<Name>, symbols: bool, numerics: bool) -> PyResult<()> {
    // First pass: walk spans, collect numeric-symbol parts, promote
    // ORG_CLASS-covered parts to LEGAL, upgrade ENT→ORG on a long
    // ORG_CLASS span.
    let mut numeric_part_hashes: HashSet<isize> = HashSet::new();
    let mut should_upgrade = false;
    {
        let name_ref = name.bind(py).borrow();
        let spans = name_ref.spans.bind(py);
        for span_item in spans.iter() {
            let span = span_item.cast::<Span>()?.borrow();
            let sym = span.symbol.bind(py).borrow();
            match sym.category {
                SymbolCategory::ORG_CLASS => {
                    if matches!(name_ref.tag, NameTypeTag::ENT) {
                        let span_len: usize = span
                            .parts
                            .bind(py)
                            .iter()
                            .map(|p| {
                                p.cast::<NamePart>()
                                    .ok()
                                    .map(|b| b.borrow().form_str().chars().count())
                                    .unwrap_or(0)
                            })
                            .sum();
                        if span_len > 2 {
                            should_upgrade = true;
                        }
                    }
                    for p_item in span.parts.bind(py).iter() {
                        let part_b = p_item.cast::<NamePart>()?;
                        let part = part_b.borrow();
                        if matches!(part.tag, NamePartTag::UNSET) {
                            drop(part);
                            part_b.borrow_mut().tag = NamePartTag::LEGAL;
                        }
                    }
                }
                SymbolCategory::NUMERIC => {
                    for p_item in span.parts.bind(py).iter() {
                        let part_b = p_item.cast::<NamePart>()?;
                        let h: isize = part_b.borrow().hash_isize();
                        numeric_part_hashes.insert(h);
                    }
                }
                _ => {}
            }
        }
    }
    if should_upgrade {
        name.bind(py).borrow_mut().tag = NameTypeTag::ORG;
    }

    // Second pass: walk parts, promote UNSET numerics → NUM (+ NUMERIC
    // symbol when `numerics`), UNSET stopwords → STOP.
    let parts_list = name.bind(py).borrow().parts.clone_ref(py);
    for item in parts_list.bind(py).iter() {
        let part_b = item.cast::<NamePart>()?;
        let (is_numeric, integer_val, form_str, current_tag, part_hash) = {
            let p = part_b.borrow();
            (
                p.numeric,
                p.integer,
                p.form_str().to_string(),
                p.tag,
                p.hash_isize(),
            )
        };
        if !matches!(current_tag, NamePartTag::UNSET) {
            continue;
        }
        if is_numeric {
            part_b.borrow_mut().tag = NamePartTag::NUM;
            if symbols && numerics && !numeric_part_hashes.contains(&part_hash) {
                if let Some(v) = integer_val {
                    let sym = Symbol::from_u32(SymbolCategory::NUMERIC, v as u32);
                    let sym_py = Py::new(py, sym)?;
                    let part_py = part_b.clone().unbind();
                    name.bind(py).borrow().apply_part(py, part_py, sym_py)?;
                }
                numeric_part_hashes.insert(part_hash);
            }
        } else if is_stopword(&form_str) {
            part_b.borrow_mut().tag = NamePartTag::STOP;
        }
    }
    Ok(())
}

/// `Name::consolidate_names` invoked through Rust code.
fn consolidate_names(py: Python<'_>, names: Vec<Py<Name>>) -> PyResult<Py<PySet>> {
    // Replicate the pymethod's HashSet logic here so we don't need
    // to go through `PyAny.try_iter`.
    let len = names.len();
    let mut kept: HashSet<usize> = (0..len).collect();
    for i in 0..len {
        if !kept.contains(&i) {
            continue;
        }
        let name_i = names[i].bind(py).borrow();
        for (j, other) in names.iter().enumerate() {
            if i == j {
                continue;
            }
            let name_j = other.bind(py).borrow();
            if name_i.contains(py, name_j)? {
                kept.remove(&j);
            }
        }
    }
    let out = PySet::empty(py)?;
    for idx in &kept {
        out.add(names[*idx].clone_ref(py))?;
    }
    Ok(out.unbind())
}

/// PyO3 wrapper.
#[pyfunction]
#[pyo3(name = "analyze_names")]
#[pyo3(signature = (type_tag, names, part_tags = None, *, infer_initials = false, symbols = true, phonetics = true, numerics = true, consolidate = true, rewrite = true))]
#[allow(clippy::too_many_arguments)]
pub fn py_analyze_names(
    py: Python<'_>,
    type_tag: NameTypeTag,
    names: Vec<String>,
    part_tags: Option<HashMap<NamePartTag, Vec<String>>>,
    infer_initials: bool,
    symbols: bool,
    phonetics: bool,
    numerics: bool,
    consolidate: bool,
    rewrite: bool,
) -> PyResult<Py<PySet>> {
    analyze_names(
        py,
        type_tag,
        names,
        part_tags.unwrap_or_default(),
        infer_initials,
        symbols,
        phonetics,
        numerics,
        consolidate,
        rewrite,
    )
}
