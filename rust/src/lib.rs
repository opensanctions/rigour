pub mod names;
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
    PySet::new(py, &text::scripts::text_scripts(text))
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

// Low-level org-types replacer. The nice Python API (Normalize
// IntFlag, Cleanup IntEnum) lives in rigour/names/org_types_rust.py
// and passes plain ints through here. Bit values must match the
// Python-side IntFlag/IntEnum definitions in rigour/text/normalize.py.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "replace_org_types_compare")]
fn py_replace_org_types_compare(text: &str, flags: u16, cleanup: u8) -> String {
    let flags = text::normalize::Normalize::from_bits_truncate(flags);
    let cleanup = match cleanup {
        1 => text::normalize::Cleanup::Strong,
        2 => text::normalize::Cleanup::Slug,
        _ => text::normalize::Cleanup::Noop,
    };
    names::org_types::replace_org_types_compare(text, flags, cleanup)
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
    Ok(())
}
