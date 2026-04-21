//! Leaf classes of the names object graph:
//!
//! - [`NamePart`] — a single tagged component of a name (token-level).
//! - [`Span`] — one or more [`NamePart`]s associated with a
//!   [`crate::names::symbol::Symbol`].

use std::hash::{DefaultHasher, Hash, Hasher};

use pyo3::prelude::*;
use pyo3::types::PyString;

use crate::names::tag::NamePartTag;
use crate::text::numbers::string_number;
use crate::text::phonetics::metaphone;
use crate::text::translit::{maybe_ascii, should_ascii};

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

/// A single tagged component of a [`crate::names::name::Name`].
///
/// Exposed attributes:
///
/// | field | type | notes |
/// |---|---|---|
/// | `form` | `str` | token text, as tokenised from the parent name |
/// | `index` | `int \| None` | position in the parent name |
/// | `tag` | [`NamePartTag`] | mutable — set by the tagging pipeline |
/// | `latinize` | `bool` | whether the form is in an admitted script |
/// | `numeric` | `bool` | whether the form is all numeric chars |
/// | `ascii` | `str \| None` | ASCII form for admitted-script parts, else `None` |
/// | `integer` | `int \| None` | parsed value for numeric parts |
/// | `comparable` | `str` | best-effort matchable form |
/// | `metaphone` | `str \| None` | phonetic key for latinisable parts, else `None` |
///
/// Equality and hashing are over `(index, form)` — the immutable
/// identity of the part. `tag` can be re-written after construction
/// without invalidating either.
#[pyclass(module = "rigour._core")]
pub struct NamePart {
    #[pyo3(get)]
    pub form: Py<PyString>,
    #[pyo3(get)]
    pub index: Option<u32>,
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
    /// Construct a `NamePart`.
    ///
    /// Args:
    ///   * `form` — the raw token text. Callers typically feed
    ///     casefolded input; no further normalisation is performed
    ///     here.
    ///   * `index` — position in the parent name, or `None` for a
    ///     free-standing part.
    ///   * `tag` — initial structural tag, defaulting to `UNSET`.
    ///   * `phonetics` — when `true`, populate `metaphone`; when
    ///     `false`, leave it `None` and skip the phonetic computation.
    ///
    /// `ascii`, `comparable`, `integer`, and `metaphone` are
    /// computed eagerly from `form` and cached.
    #[new]
    #[pyo3(signature = (form, index = None, tag = NamePartTag::UNSET, phonetics = true))]
    pub fn new(
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

        let hash = hash_namepart(index, &form_str);

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

    /// True if this part's tag is structurally compatible with the
    /// other part's tag. See [`NamePartTag::can_match`].
    fn can_match(&self, other: PyRef<'_, NamePart>) -> bool {
        self.tag.can_match(other.tag)
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        match other.extract::<PyRef<'_, NamePart>>() {
            Ok(n) => n.index == self.index && n.form_str == self.form_str,
            Err(_) => false,
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

    /// Return `parts` sorted by the canonical display order of their
    /// tags (see [`crate::names::tag::NAME_TAGS_ORDER`]). The sort is
    /// stable.
    #[classmethod]
    fn tag_sort(
        _cls: &Bound<'_, pyo3::types::PyType>,
        py: Python<'_>,
        parts: Vec<Py<NamePart>>,
    ) -> Vec<Py<NamePart>> {
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
    /// Rust-only accessor for the token text. Cheaper than
    /// `self.form.bind(py).extract::<String>()` when you already hold
    /// a `&NamePart`.
    pub fn form_str(&self) -> &str {
        &self.form_str
    }

    /// Rust-only accessor for the cached hash. Used for part-identity
    /// tracking in the analyze pipeline.
    pub fn hash_isize(&self) -> isize {
        self.hash
    }
}

fn hash_namepart(index: Option<u32>, form: &str) -> isize {
    let mut hasher = DefaultHasher::new();
    index.hash(&mut hasher);
    form.hash(&mut hasher);
    hasher.finish() as isize
}

/// A contiguous group of [`NamePart`]s annotated with a
/// [`crate::names::symbol::Symbol`] — the tagger's output unit.
///
/// The `parts` list holds the *same* `Py<NamePart>` references that
/// live in the parent [`crate::names::name::Name`]'s `.parts`, so
/// `span.parts[0] is name.parts[i]` is True from Python.
///
/// `comparable` and `__len__` (total character count across the
/// parts' `form` strings) are precomputed at construction.
#[pyclass(module = "rigour._core")]
pub struct Span {
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
    pub fn new(
        py: Python<'_>,
        parts: Vec<Py<NamePart>>,
        symbol: Py<crate::names::symbol::Symbol>,
    ) -> PyResult<Self> {
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

        let hash = hash_span(py, &parts, &symbol);
        let parts_list = pyo3::types::PyList::new(py, &parts)?.unbind();

        Ok(Self {
            parts: parts_list,
            symbol,
            comparable: comparable_py,
            len_chars,
            hash,
        })
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

fn hash_span(
    py: Python<'_>,
    parts: &[Py<NamePart>],
    symbol: &Py<crate::names::symbol::Symbol>,
) -> isize {
    let mut hasher = DefaultHasher::new();
    for p in parts {
        let h = p.bind(py).borrow().hash;
        h.hash(&mut hasher);
    }
    symbol.bind(py).borrow().hash(&mut hasher);
    hasher.finish() as isize
}
