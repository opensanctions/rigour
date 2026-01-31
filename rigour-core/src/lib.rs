/// rigour-core: Performance-critical Rust implementation for the rigour Python library.
///
/// This crate provides high-performance implementations of data normalization and
/// validation functions, with Python bindings via PyO3.

mod common;
mod addresses;
mod names;

use pyo3::prelude::*;
use common::ascii_text as ascii_text_impl;

/// Normalize an address string for comparison.
///
/// This function performs aggressive normalization suitable for matching but not display.
///
/// Args:
///     address (str): The address string to normalize
///     latinize (bool): Whether to convert non-Latin characters to ASCII
///     min_length (int): Minimum length for the normalized result
///
/// Returns:
///     Optional[str]: The normalized address, or None if below minimum length
///
/// Examples:
///     >>> from rigour._core import normalize_address
///     >>> normalize_address("123 Main St.", False, 4)
///     '123 main st'
///     >>> normalize_address("abc", False, 4)
///     None
#[pyfunction]
#[pyo3(signature = (address, latinize=false, min_length=4))]
fn normalize_address(
    address: &str,
    latinize: bool,
    min_length: usize,
) -> PyResult<Option<String>> {
    Ok(addresses::normalize_address(address, latinize, min_length))
}

/// Transliterate text to ASCII.
///
/// This function converts text from any script to ASCII using ICU transliteration.
/// It matches the behavior of Python's normality.ascii_text().
///
/// Args:
///     text (str): The text to transliterate
///
/// Returns:
///     str: ASCII-only string
///
/// Examples:
///     >>> from rigour._core import ascii_text
///     >>> ascii_text("Café")
///     'Cafe'
///     >>> ascii_text("Порошенко")
///     'Porosenko'
///     >>> ascii_text("əhməd")
///     'ahmad'
#[pyfunction]
fn ascii_text(text: &str) -> PyResult<String> {
    Ok(ascii_text_impl(text))
}

/// Split a person or entity's name into name parts.
///
/// Args:
///     text (str): The name string to tokenize
///     token_min_length (int): Minimum length for tokens (default: 1)
///
/// Returns:
///     List[str]: Vector of name part strings
///
/// Examples:
///     >>> from rigour._core import tokenize_name
///     >>> tokenize_name("John Smith")
///     ['John', 'Smith']
///     >>> tokenize_name("O'Brien")
///     ['OBrien']
#[pyfunction]
#[pyo3(signature = (text, token_min_length=1))]
fn tokenize_name(text: &str, token_min_length: usize) -> PyResult<Vec<String>> {
    Ok(names::tokenize_name(text, token_min_length))
}

/// Prepare a name for tokenization and matching.
///
/// Converts to lowercase using Unicode case folding.
///
/// Args:
///     name (str): The name string to prenormalize
///
/// Returns:
///     str: Prenormalized name string (casefolded)
///
/// Examples:
///     >>> from rigour._core import prenormalize_name
///     >>> prenormalize_name("John SMITH")
///     'john smith'
///     >>> prenormalize_name("MÜLLER")
///     'müller'
#[pyfunction]
fn prenormalize_name(name: &str) -> PyResult<String> {
    Ok(names::prenormalize_name(name))
}

/// Normalize a name for tokenization and matching.
///
/// This function prenormalizes (casefolds) the name, tokenizes it,
/// joins tokens with separator, and returns None if result is empty.
///
/// Args:
///     name (str): The name string to normalize
///     sep (str): Token separator (default: " ")
///
/// Returns:
///     Optional[str]: Normalized name string, or None if empty
///
/// Examples:
///     >>> from rigour._core import normalize_name
///     >>> normalize_name("John SMITH")
///     'john smith'
///     >>> normalize_name("O'Brien")
///     'obrien'
///     >>> normalize_name("   ")
///     None
#[pyfunction]
#[pyo3(signature = (name, sep=" "))]
fn normalize_name(name: &str, sep: &str) -> PyResult<Option<String>> {
    Ok(names::normalize_name(name, sep))
}

/// Python module definition.
///
/// This module is imported as `rigour._core` in Python.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Address normalization functions
    m.add_function(wrap_pyfunction!(normalize_address, m)?)?;

    // Text transliteration functions
    m.add_function(wrap_pyfunction!(ascii_text, m)?)?;

    // Name processing functions
    m.add_function(wrap_pyfunction!(tokenize_name, m)?)?;
    m.add_function(wrap_pyfunction!(prenormalize_name, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_name, m)?)?;

    Ok(())
}
