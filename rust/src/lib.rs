pub mod phonetics;

#[cfg(feature = "python")]
use pyo3::prelude::*;

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
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_metaphone, m)?)?;
    m.add_function(wrap_pyfunction!(py_soundex, m)?)?;
    Ok(())
}
