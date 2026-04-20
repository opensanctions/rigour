// Rust-backed `NamePart` and `Span` — the two leaf classes of the
// `rigour.names` object graph. Python wrappers at
// `rigour/names/part.py` are thin re-exports.
//
// Linear eager pipeline at `NamePart::new`:
//   1. form (input)
//   2. index (input, Option<u32>)
//   3. tag (input, NamePartTag, default UNSET)
//   4. numeric = every char numeric
//   5. latinize = should_ascii(form)
//   6. integer = if numeric { string_number -> int if is_integer }
//   7. ascii = per the Python impl, now over maybe_ascii instead of
//             normality.ascii_text. Non-latinize parts resolve to
//             None (was previously whatever ICU produced) — matches
//             the narrow-translit scope documented in
//             `plans/rust-minimal-translit.md`.
//   8. comparable = numeric→str(integer); !latinize→form; else ascii|form
//   9. metaphone = if phonetics && latinize && !numeric && len(ascii)>2
//
// All fields cached on the struct; Python attribute reads are
// plain INCREFs / copies.

use pyo3::prelude::*;
use pyo3::types::{PyString, PyTuple};

use crate::names::tag::{NAME_TAGS_ORDER, NamePartTag};
use crate::text::numbers::string_number;
use crate::text::phonetics::metaphone;
use crate::text::translit::{maybe_ascii, should_ascii};

/// Strip non-alphanumeric chars from a string; return None if the
/// result is empty. Mirrors `"".join(c for c in s if c.isalnum())`
/// in the Python `NamePart.ascii` body.
fn strip_nonalnum(text: &str) -> Option<String> {
    let out: String = text.chars().filter(|c| c.is_alphanumeric()).collect();
    if out.is_empty() { None } else { Some(out) }
}

fn compute_ascii(
    form: &str,
    numeric: bool,
    latinize: bool,
    integer: Option<i64>,
) -> Option<String> {
    if numeric {
        return integer.map(|v| v.to_string());
    }
    if !latinize {
        return None;
    }
    if form.is_ascii() {
        return strip_nonalnum(form);
    }
    let translit = maybe_ascii(form, false);
    strip_nonalnum(&translit)
}

fn compute_comparable(
    form: &str,
    numeric: bool,
    latinize: bool,
    integer: Option<i64>,
    ascii: Option<&str>,
) -> String {
    if numeric {
        return integer.map(|v| v.to_string()).unwrap_or_default();
    }
    if !latinize {
        return form.to_string();
    }
    match ascii {
        Some(a) => a.to_string(),
        None => form.to_string(),
    }
}

fn compute_metaphone(
    phonetics: bool,
    latinize: bool,
    numeric: bool,
    ascii: Option<&str>,
) -> Option<String> {
    if !phonetics || !latinize || numeric {
        return None;
    }
    let text = ascii?;
    if text.chars().count() <= 2 {
        return None;
    }
    Some(metaphone(text))
}

/// A tagged component of a name (e.g. a given name, family name, or
/// stop word). See `rigour/names/part.py` for the Python-side
/// documentation.
#[pyclass(module = "rigour._core")]
pub struct NamePart {
    #[pyo3(get)]
    pub form: Py<PyString>,
    #[pyo3(get)]
    pub index: Option<u32>,
    /// Mutable — the tagger rewrites this after construction.
    #[pyo3(get, set)]
    pub tag: NamePartTag,
    #[pyo3(get)]
    pub latinize: bool,
    #[pyo3(get)]
    pub numeric: bool,
    #[pyo3(get)]
    pub ascii: Option<Py<PyString>>,
    #[pyo3(get)]
    pub integer: Option<i64>,
    #[pyo3(get)]
    pub comparable: Py<PyString>,
    #[pyo3(get)]
    pub metaphone: Option<Py<PyString>>,
    form_str: String,
    hash: isize,
}

#[pymethods]
impl NamePart {
    /// Build a `NamePart` from `form`.
    ///
    /// `form` is the raw text (expected casefolded by the caller, as
    /// it is across the rigour pipeline). `index` is the part's
    /// position in the parent `Name` if any. `tag` defaults to
    /// `NamePartTag.UNSET`. `phonetics` gates metaphone computation.
    #[new]
    #[pyo3(signature = (form, index = None, tag = NamePartTag::UNSET, phonetics = true))]
    fn new(
        py: Python<'_>,
        form: &str,
        index: Option<u32>,
        tag: NamePartTag,
        phonetics: bool,
    ) -> Self {
        Self::build(py, form, index, tag, phonetics)
    }

    fn can_match(&self, other: PyRef<'_, NamePart>) -> bool {
        self.tag.can_match(other.tag)
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        // Mirror the Python impl: compare precomputed hash. Duck-type
        // on `_hash` so pre-port Python NamePart instances that may
        // still be around (tests, downstream unpickled state) also
        // compare correctly during a migration window.
        match other.getattr("_hash") {
            Ok(h) => match h.extract::<isize>() {
                Ok(h) => h == self.hash,
                Err(_) => false,
            },
            Err(_) => match other.extract::<PyRef<'_, NamePart>>() {
                Ok(n) => n.hash == self.hash,
                Err(_) => false,
            },
        }
    }

    fn __hash__(&self) -> isize {
        self.hash
    }

    fn __len__(&self) -> usize {
        self.form_str.chars().count()
    }

    fn __repr__(&self) -> String {
        format!(
            "<NamePart('{}', {}, '{}')>",
            self.form_str,
            self.index
                .map(|i| i.to_string())
                .unwrap_or_else(|| "None".to_string()),
            self.tag.value(),
        )
    }

    /// Expose the cached hash as `_hash` so the legacy
    /// `other._hash == self._hash` equality check from pre-port
    /// Python code keeps working across the boundary.
    #[getter]
    fn _hash(&self) -> isize {
        self.hash
    }

    /// Stable sort of `parts` by `NAME_TAGS_ORDER` position of each
    /// part's tag. Mirrors the pre-port Python classmethod.
    #[classmethod]
    fn tag_sort(
        _cls: &Bound<'_, pyo3::types::PyType>,
        py: Python<'_>,
        parts: Vec<Py<NamePart>>,
    ) -> Vec<Py<NamePart>> {
        let _ = NAME_TAGS_ORDER; // silence unused-import lint in non-test builds
        let mut indexed: Vec<(usize, Py<NamePart>)> = parts
            .into_iter()
            .map(|p| {
                let pos = p.bind(py).borrow().tag.order_index();
                (pos, p)
            })
            .collect();
        indexed.sort_by_key(|(pos, _)| *pos);
        indexed.into_iter().map(|(_, p)| p).collect()
    }
}

impl NamePart {
    /// Internal constructor — callable from Rust without PyO3 getter
    /// ceremony. Used by `Name::new` when tokenising.
    pub fn build(
        py: Python<'_>,
        form: &str,
        index: Option<u32>,
        tag: NamePartTag,
        phonetics: bool,
    ) -> Self {
        let form_str = form.to_string();
        let numeric = !form_str.is_empty() && form_str.chars().all(|c| c.is_numeric());
        let latinize = should_ascii(form);
        let integer = if numeric {
            match string_number(form) {
                Some(v) if v.is_finite() && v.fract() == 0.0 => {
                    if v >= i64::MIN as f64 && v <= i64::MAX as f64 {
                        Some(v as i64)
                    } else {
                        None
                    }
                }
                _ => None,
            }
        } else {
            None
        };
        let ascii_s = compute_ascii(&form_str, numeric, latinize, integer);
        let comparable_s =
            compute_comparable(&form_str, numeric, latinize, integer, ascii_s.as_deref());
        let metaphone_s = compute_metaphone(phonetics, latinize, numeric, ascii_s.as_deref());

        let hash = hash_namepart(py, index, &form_str);

        let form_py = PyString::new(py, &form_str).unbind();
        let ascii_py = ascii_s.as_ref().map(|s| PyString::new(py, s).unbind());
        let comparable_py = PyString::new(py, &comparable_s).unbind();
        let metaphone_py = metaphone_s.as_ref().map(|s| PyString::new(py, s).unbind());

        Self {
            form: form_py,
            index,
            tag,
            latinize,
            numeric,
            ascii: ascii_py,
            integer,
            comparable: comparable_py,
            metaphone: metaphone_py,
            form_str,
            hash,
        }
    }

    pub fn form_str(&self) -> &str {
        &self.form_str
    }

    /// Internal accessor for the cached hash. Useful for Rust-internal
    /// part-identity tracking (e.g. in `names::analyze::infer_part_tags`).
    pub fn hash_isize(&self) -> isize {
        self.hash
    }
}

fn hash_namepart(py: Python<'_>, index: Option<u32>, form: &str) -> isize {
    // Mirror Python's `hash((index, form))`. Tuple hashing is handled
    // by CPython — cheaper to call through than to reimplement.
    let idx_obj: Py<PyAny> = match index {
        Some(i) => i.into_pyobject(py).unwrap().unbind().into_any(),
        None => py.None(),
    };
    let form_obj = PyString::new(py, form).unbind();
    let Ok(tup) = PyTuple::new(py, [idx_obj, form_obj.into_any()]) else {
        return 0;
    };
    tup.hash().unwrap_or(0)
}

/// A symbol applied to one or more parts of a `Name`.
#[pyclass(module = "rigour._core")]
pub struct Span {
    /// Shared Python list of `NamePart`s — the same `Py<NamePart>`
    /// refs live in `Name.parts`. Identity is preserved
    /// (`span.parts[0] is name.parts[i]` is `True` from Python).
    #[pyo3(get)]
    pub parts: Py<pyo3::types::PyList>,
    #[pyo3(get)]
    pub symbol: Py<crate::names::symbol::Symbol>,
    #[pyo3(get)]
    pub comparable: Py<PyString>,
    len_chars: usize,
    hash: isize,
}

#[pymethods]
impl Span {
    #[new]
    fn new(
        py: Python<'_>,
        parts: Vec<Py<NamePart>>,
        symbol: Py<crate::names::symbol::Symbol>,
    ) -> PyResult<Self> {
        Self::build(py, parts, symbol)
    }

    fn __len__(&self) -> usize {
        self.len_chars
    }

    fn __hash__(&self) -> isize {
        self.hash
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        match other.extract::<PyRef<'_, Span>>() {
            Ok(s) => s.hash == self.hash,
            Err(_) => false,
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let parts_repr: String = self.parts.bind(py).repr()?.extract()?;
        let sym_repr: String = self.symbol.bind(py).repr()?.extract()?;
        Ok(format!("<Span({}, {})>", parts_repr, sym_repr))
    }
}

impl Span {
    pub fn build(
        py: Python<'_>,
        parts: Vec<Py<NamePart>>,
        symbol: Py<crate::names::symbol::Symbol>,
    ) -> PyResult<Self> {
        // Precompute comparable and char-count length from the parts.
        let mut segments: Vec<String> = Vec::with_capacity(parts.len());
        let mut len_chars: usize = 0;
        for part_ref in &parts {
            let part = part_ref.bind(py).borrow();
            let comparable: String = part.comparable.bind(py).extract()?;
            segments.push(comparable);
            len_chars += part.form_str.chars().count();
        }
        let comparable_str = segments.join(" ");
        let comparable_py = PyString::new(py, &comparable_str).unbind();

        let hash = hash_span(py, &parts, &symbol)?;
        let parts_list = pyo3::types::PyList::new(py, &parts)?.unbind();

        Ok(Self {
            parts: parts_list,
            symbol,
            comparable: comparable_py,
            len_chars,
            hash,
        })
    }
}

fn hash_span(
    py: Python<'_>,
    parts: &[Py<NamePart>],
    symbol: &Py<crate::names::symbol::Symbol>,
) -> PyResult<isize> {
    // Mirror Python `hash((tuple(parts), symbol))`. Python's hash on a
    // tuple of NameParts is computed from their `__hash__`; since
    // NamePart exposes `__hash__` in Rust, the tuple hash just calls
    // them. We build the tuple in Python and hash it once.
    let parts_tup = PyTuple::new(py, parts)?;
    let full = PyTuple::new(py, [parts_tup.as_any(), symbol.bind(py).as_any()])?;
    full.hash()
}
