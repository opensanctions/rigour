pub mod names;
pub mod territories;
pub mod text;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PySet;

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "metaphone")]
fn py_metaphone(token: &str) -> String {
    text::phonetics::metaphone(token)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "soundex")]
fn py_soundex(token: &str) -> String {
    text::phonetics::soundex(token)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "codepoint_script")]
fn py_codepoint_script(cp: u32) -> Option<&'static str> {
    text::scripts::codepoint_script(cp)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "text_scripts")]
fn py_text_scripts<'py>(py: Python<'py>, text: &str) -> PyResult<Bound<'py, PySet>> {
    PySet::new(py, text::scripts::text_scripts(text))
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "latinize_text")]
fn py_latinize_text(text: &str) -> String {
    text::transliterate::latinize_text(text)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "ascii_text")]
fn py_ascii_text(text: &str) -> String {
    text::transliterate::ascii_text(text)
}

// Low-level normalize. The nice Python API (IntFlag for Normalize, IntEnum
// for Cleanup) lives in rigour/text/normalize.py and passes plain ints
// through this function. The flag bit values and cleanup tags must match
// the Python-side IntFlag/IntEnum definitions.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "_normalize")]
fn py_normalize(text: &str, flags: u16, cleanup: u8) -> Option<String> {
    let flags = text::normalize::Normalize::from_bits_truncate(flags);
    let cleanup = match cleanup {
        1 => text::normalize::Cleanup::Strong,
        2 => text::normalize::Cleanup::Slug,
        _ => text::normalize::Cleanup::Noop,
    };
    text::normalize::normalize(text, flags, cleanup)
}

// Minimal PyO3 function used by benchmarks/bench_transliteration.py to
// measure pure FFI overhead (String in, String out) independent of any
// transliteration work.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "_ffi_noop")]
fn py_ffi_noop(text: &str) -> String {
    text.to_string()
}

// Low-level org-types replacers. The nice Python API (Normalize
// IntFlag, Cleanup IntEnum) lives in rigour/names/org_types.py and
// passes plain ints through here. Bit values must match the Python-
// side IntFlag/IntEnum definitions in rigour/text/normalize.py.
#[cfg(feature = "python")]
fn _decode_flags(
    flags: u16,
    cleanup: u8,
) -> (text::normalize::Normalize, text::normalize::Cleanup) {
    let flags = text::normalize::Normalize::from_bits_truncate(flags);
    let cleanup = match cleanup {
        1 => text::normalize::Cleanup::Strong,
        2 => text::normalize::Cleanup::Slug,
        _ => text::normalize::Cleanup::Noop,
    };
    (flags, cleanup)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "replace_org_types_compare")]
fn py_replace_org_types_compare(text: &str, flags: u16, cleanup: u8, generic: bool) -> String {
    let (flags, cleanup) = _decode_flags(flags, cleanup);
    names::org_types::replace_compare(text, flags, cleanup, generic)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "replace_org_types_display")]
fn py_replace_org_types_display(text: &str, flags: u16, cleanup: u8) -> String {
    let (flags, cleanup) = _decode_flags(flags, cleanup);
    names::org_types::replace_display(text, flags, cleanup)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "remove_org_types")]
fn py_remove_org_types(text: &str, flags: u16, cleanup: u8, replacement: &str) -> String {
    let (flags, cleanup) = _decode_flags(flags, cleanup);
    names::org_types::remove(text, flags, cleanup, replacement)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "extract_org_types")]
fn py_extract_org_types(
    text: &str,
    flags: u16,
    cleanup: u8,
    generic: bool,
) -> Vec<(String, String)> {
    let (flags, cleanup) = _decode_flags(flags, cleanup);
    names::org_types::extract(text, flags, cleanup, generic)
}

// Resource accessors — plain `list[str]` / `dict` returners that
// Python modules read once at import time. Naming convention:
// `<name>_list` for flat-list accessors, `<name>_dict` for dict-shaped.
// See `plans/rust-tagger.md` for the data-migration classification.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "stopwords_list")]
fn py_stopwords_list() -> Vec<String> {
    text::stopwords::stopwords_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "nullwords_list")]
fn py_nullwords_list() -> Vec<String> {
    text::stopwords::nullwords_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "nullplaces_list")]
fn py_nullplaces_list() -> Vec<String> {
    text::stopwords::nullplaces_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "person_name_prefixes_list")]
fn py_person_name_prefixes_list() -> Vec<String> {
    names::stopwords::person_name_prefixes_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "org_name_prefixes_list")]
fn py_org_name_prefixes_list() -> Vec<String> {
    names::stopwords::org_name_prefixes_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "obj_name_prefixes_list")]
fn py_obj_name_prefixes_list() -> Vec<String> {
    names::stopwords::obj_name_prefixes_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "name_split_phrases_list")]
fn py_name_split_phrases_list() -> Vec<String> {
    names::stopwords::name_split_phrases_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "generic_person_names_list")]
fn py_generic_person_names_list() -> Vec<String> {
    names::stopwords::generic_person_names_list()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "ordinals_dict")]
fn py_ordinals_dict() -> std::collections::HashMap<u32, Vec<String>> {
    text::ordinals::ordinals_dict()
}

// The full decompressed person-names corpus as one string. Each call
// allocates a fresh `PyString` (the corpus is ~8.5 MB of text), so
// Python consumers read it once and iterate locally. Will be retired
// when the tagger ports to Rust (step 8 of plans/rust-tagger.md) —
// at which point the Rust side parses `names::person_names::raw()`
// directly without crossing the FFI.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "person_names_text")]
fn py_person_names_text() -> &'static str {
    names::person_names::raw()
}

// The full territory database as raw JSONL. Python consumers in
// `rigour.territories.*` parse line-by-line with orjson at import
// time (and under `@cache`-decorated index builders), so one ~500 KB
// PyString allocation per call is fine. The future Rust tagger
// reads `territories::raw()` directly without crossing the FFI.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "territories_jsonl")]
fn py_territories_jsonl() -> &'static str {
    territories::raw()
}

// Low-level tagger matchers. Python wrappers (`tag_org_name` /
// `tag_person_name` in rigour/names/tagging.py) call these and
// apply each (phrase, symbol) pair to the Name via apply_phrase,
// then run `_infer_part_tags` locally. See plans/rust-tagger.md
// step 8.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "tag_org_matches")]
fn py_tag_org_matches(text: &str, flags: u16, cleanup: u8) -> Vec<(String, names::symbol::Symbol)> {
    let (flags, cleanup) = _decode_flags(flags, cleanup);
    names::tagger::get_tagger(names::tagger::TaggerKind::Org, flags, cleanup).tag(text)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "tag_person_matches")]
fn py_tag_person_matches(
    text: &str,
    flags: u16,
    cleanup: u8,
) -> Vec<(String, names::symbol::Symbol)> {
    let (flags, cleanup) = _decode_flags(flags, cleanup);
    names::tagger::get_tagger(names::tagger::TaggerKind::Person, flags, cleanup).tag(text)
}

#[cfg(feature = "python")]
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_metaphone, m)?)?;
    m.add_function(wrap_pyfunction!(py_soundex, m)?)?;
    m.add_function(wrap_pyfunction!(py_codepoint_script, m)?)?;
    m.add_function(wrap_pyfunction!(py_text_scripts, m)?)?;
    m.add_function(wrap_pyfunction!(py_latinize_text, m)?)?;
    m.add_function(wrap_pyfunction!(py_ascii_text, m)?)?;
    m.add_function(wrap_pyfunction!(py_normalize, m)?)?;
    m.add_function(wrap_pyfunction!(py_ffi_noop, m)?)?;
    m.add_function(wrap_pyfunction!(py_replace_org_types_compare, m)?)?;
    m.add_function(wrap_pyfunction!(py_replace_org_types_display, m)?)?;
    m.add_function(wrap_pyfunction!(py_remove_org_types, m)?)?;
    m.add_function(wrap_pyfunction!(py_extract_org_types, m)?)?;
    m.add_function(wrap_pyfunction!(py_stopwords_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_nullwords_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_nullplaces_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_person_name_prefixes_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_org_name_prefixes_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_obj_name_prefixes_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_name_split_phrases_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_generic_person_names_list, m)?)?;
    m.add_function(wrap_pyfunction!(py_ordinals_dict, m)?)?;
    m.add_function(wrap_pyfunction!(py_person_names_text, m)?)?;
    m.add_function(wrap_pyfunction!(py_territories_jsonl, m)?)?;
    m.add_function(wrap_pyfunction!(py_tag_org_matches, m)?)?;
    m.add_function(wrap_pyfunction!(py_tag_person_matches, m)?)?;
    m.add_class::<names::symbol::Symbol>()?;
    m.add_class::<names::symbol::SymbolCategory>()?;
    Ok(())
}
