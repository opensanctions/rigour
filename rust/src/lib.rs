pub mod phonetics;
pub mod scripts;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PySet;

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "metaphone")]
fn py_metaphone(token: &str) -> String {
    phonetics::metaphone(token)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "soundex")]
fn py_soundex(token: &str) -> String {
    phonetics::soundex(token)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "codepoint_script")]
fn py_codepoint_script(cp: u32) -> Option<&'static str> {
    scripts::codepoint_script(cp)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "text_scripts")]
fn py_text_scripts<'py>(py: Python<'py>, text: &str) -> PyResult<Bound<'py, PySet>> {
    PySet::new(py, &scripts::text_scripts(text))
}

#[cfg(feature = "python")]
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_metaphone, m)?)?;
    m.add_function(wrap_pyfunction!(py_soundex, m)?)?;
    m.add_function(wrap_pyfunction!(py_codepoint_script, m)?)?;
    m.add_function(wrap_pyfunction!(py_text_scripts, m)?)?;
    Ok(())
}
