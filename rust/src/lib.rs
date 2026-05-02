pub mod constants;
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
#[pyo3(name = "common_scripts")]
fn py_common_scripts<'py>(py: Python<'py>, a: &str, b: &str) -> PyResult<Bound<'py, PySet>> {
    PySet::new(py, text::scripts::common_scripts(a, b))
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "should_ascii")]
fn py_should_ascii(text: &str) -> bool {
    text::translit::should_ascii(text)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "maybe_ascii", signature = (text, drop=false))]
fn py_maybe_ascii(text: &str, drop: bool) -> String {
    text::translit::maybe_ascii(text, drop)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "tokenize_name", signature = (text, token_min_length=1))]
fn py_tokenize_name(text: &str, token_min_length: usize) -> Vec<String> {
    text::tokenize::tokenize_name(text, token_min_length)
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

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "string_number")]
fn py_string_number(text: &str) -> Option<f64> {
    text::numbers::string_number(text)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "pick_name")]
fn py_pick_name(names: Vec<String>) -> Option<String> {
    let refs: Vec<&str> = names.iter().map(String::as_str).collect();
    names::pick::pick_name(&refs)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "pick_case")]
fn py_pick_case(names: Vec<String>) -> Option<String> {
    let refs: Vec<&str> = names.iter().map(String::as_str).collect();
    names::pick::pick_case(&refs)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "reduce_names")]
fn py_reduce_names(names: Vec<String>) -> Vec<String> {
    let refs: Vec<&str> = names.iter().map(String::as_str).collect();
    names::pick::reduce_names(&refs)
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

// The full territory database as raw JSONL. Python consumers in
// `rigour.territories.*` parse line-by-line with orjson at import
// time under `@cache`-decorated index builders, so the FFI cost is
// paid exactly once per process. Returning `String` (rather than
// `&'static str` pointing into a Rust-side static) hands the buffer
// to PyO3 which copies into a `PyString`; the Rust-side allocation
// drops, leaving only Python's copy resident.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "territories_jsonl")]
fn py_territories_jsonl() -> String {
    territories::decompressed()
}

#[cfg(feature = "python")]
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_metaphone, m)?)?;
    m.add_function(wrap_pyfunction!(py_soundex, m)?)?;
    m.add_function(wrap_pyfunction!(py_codepoint_script, m)?)?;
    m.add_function(wrap_pyfunction!(py_text_scripts, m)?)?;
    m.add_function(wrap_pyfunction!(py_common_scripts, m)?)?;
    m.add_function(wrap_pyfunction!(py_should_ascii, m)?)?;
    m.add_function(wrap_pyfunction!(py_maybe_ascii, m)?)?;
    m.add_function(wrap_pyfunction!(py_tokenize_name, m)?)?;
    m.add_function(wrap_pyfunction!(py_normalize, m)?)?;
    m.add_function(wrap_pyfunction!(py_string_number, m)?)?;
    m.add_function(wrap_pyfunction!(py_pick_name, m)?)?;
    m.add_function(wrap_pyfunction!(py_pick_case, m)?)?;
    m.add_function(wrap_pyfunction!(py_reduce_names, m)?)?;
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
    m.add_function(wrap_pyfunction!(py_territories_jsonl, m)?)?;
    m.add_function(wrap_pyfunction!(names::analyze::py_analyze_names, m)?)?;
    m.add_function(wrap_pyfunction!(
        names::ordering::py_align_person_name_order,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(names::pairing::py_pair_symbols, m)?)?;
    m.add_function(wrap_pyfunction!(names::compare::py_compare_parts, m)?)?;
    m.add_class::<names::compare::CompareConfig>()?;
    m.add_class::<names::alignment::Alignment>()?;
    m.add_class::<names::symbol::Symbol>()?;
    m.add_class::<names::symbol::SymbolCategory>()?;
    m.add_class::<names::tag::NameTypeTag>()?;
    m.add_class::<names::tag::NamePartTag>()?;
    m.add_class::<names::part::NamePart>()?;
    m.add_class::<names::part::Span>()?;
    m.add_class::<names::name::Name>()?;
    Ok(())
}
