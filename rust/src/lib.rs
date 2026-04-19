pub mod distance;
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
#[pyfunction]
#[pyo3(name = "levenshtein", signature = (left, right, score_cutoff=None))]
fn py_levenshtein(left: &str, right: &str, score_cutoff: Option<usize>) -> usize {
    distance::levenshtein(left, right, score_cutoff)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "dam_levenshtein", signature = (left, right, score_cutoff=None))]
fn py_dam_levenshtein(left: &str, right: &str, score_cutoff: Option<usize>) -> usize {
    distance::dam_levenshtein(left, right, score_cutoff)
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "jaro_winkler_similarity")]
fn py_jaro_winkler_similarity(left: &str, right: &str) -> f64 {
    distance::jaro_winkler_similarity(left, right)
}

#[cfg(feature = "python")]
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(py_metaphone, m)?)?;
    m.add_function(wrap_pyfunction!(py_soundex, m)?)?;
    m.add_function(wrap_pyfunction!(py_levenshtein, m)?)?;
    m.add_function(wrap_pyfunction!(py_dam_levenshtein, m)?)?;
    m.add_function(wrap_pyfunction!(py_jaro_winkler_similarity, m)?)?;
    Ok(())
}
