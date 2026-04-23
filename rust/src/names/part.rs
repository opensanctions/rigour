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
    // Metaphone is ASCII-only; non-ASCII input (e.g. `ĸ` surviving
    // `maybe_ascii` because it's already Latin) would cause the
    // `rphonetic` crate to panic on byte-indexed slicing. The
    // wrapper in `text::phonetics::metaphone` also short-circuits,
    // but we surface the skip as `None` here so the field stays
    // `None` rather than `Some("")`.
    if !text.is_ascii() {
        return None;
    }
    Some(metaphone(text))
}

/// A single tagged component of a [`crate::names::name::Name`].
///
/// Equality and hashing are over `(index, form)` — the immutable
/// identity of the part. `tag` can be re-written after construction
/// without invalidating either.
#[pyclass(module = "rigour._core")]
pub struct NamePart {
    /// Token text, as tokenised from the parent name's form.
    #[pyo3(get)]
    pub form: Py<PyString>,
    /// Position of this part within the parent name's `parts` list.
    #[pyo3(get)]
    pub index: u32,
    /// Structural role of this part. Set by the tagging pipeline;
    /// `UNSET` at construction.
    #[pyo3(get, set)]
    pub tag: NamePartTag,
    /// `True` if `form` is in an admitted-script set (Latin,
    /// Cyrillic, Greek, Armenian, Georgian, Hangul) and thus can
    /// be meaningfully ASCII-ified.
    #[pyo3(get)]
    pub latinize: bool,
    /// `True` if `form` is entirely numeric characters.
    #[pyo3(get)]
    pub numeric: bool,
    /// ASCII-ified form of `form` for admitted-script parts;
    /// `None` when the part is outside the admitted scripts or
    /// reduces to empty after stripping non-alphanumerics.
    #[pyo3(get)]
    pub ascii: Option<Py<PyString>>,
    /// Parsed integer value for numeric parts, or `None` when the
    /// part isn't numeric or doesn't fit an `i64`.
    #[pyo3(get)]
    pub integer: Option<i64>,
    /// Best-effort matchable form: integer string for numerics,
    /// `form` for non-latinize parts, `ascii` otherwise.
    #[pyo3(get)]
    pub comparable: Py<PyString>,
    /// Metaphone phonetic key, or `None` when phonetics were
    /// disabled at construction or the part doesn't qualify
    /// (non-latinize, numeric, or shorter than three characters).
    #[pyo3(get)]
    pub metaphone: Option<Py<PyString>>,
    form_str: String,
    comparable_str: String,
    hash: isize,
}

#[pymethods]
impl NamePart {
    /// Construct a `NamePart`.
    ///
    /// `form` is the raw token text; callers feed casefolded input.
    /// `index` is the part's position in the parent name's `parts`
    /// list. `tag` is the initial structural tag (usually left as
    /// `UNSET` and filled in later). `phonetics=false` skips the
    /// metaphone computation — leaves the field as `None`.
    ///
    /// `ascii`, `comparable`, `integer`, and `metaphone` are
    /// computed eagerly from `form` and cached.
    #[new]
    #[pyo3(signature = (form, index, tag = NamePartTag::UNSET, phonetics = true))]
    pub fn new(py: Python<'_>, form: &str, index: u32, tag: NamePartTag, phonetics: bool) -> Self {
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
        let comparable_str =
            compute_comparable(&form_str, numeric, latinize, integer, ascii_s.as_deref());
        let metaphone_s = compute_metaphone(phonetics, latinize, numeric, ascii_s.as_deref());

        let hash = hash_namepart(index, &form_str);

        let form_py = PyString::new(py, &form_str).unbind();
        let ascii_py = ascii_s.as_ref().map(|s| PyString::new(py, s).unbind());
        let comparable_py = PyString::new(py, &comparable_str).unbind();
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
            comparable_str,
            hash,
        }
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
            self.index,
            self.tag.value(),
        )
    }

    /// Sort name parts into canonical display order.
    ///
    /// Used when rendering a name back out for humans: honorifics
    /// come first, then given names, middle, family, suffixes,
    /// legal forms, and stopwords — independent of the input word
    /// order. A tokeniser might hand the parts over as "Guttenberg
    /// zu Karl-Theodor" (order from the source data); `tag_sort`
    /// restores "Karl-Theodor zu Guttenberg" shape once the parts
    /// have been tagged. Sort is stable across parts with the same
    /// tag; see [`crate::names::tag::NAME_TAGS_ORDER`] for the full
    /// ordering.
    #[classmethod]
    fn tag_sort(
        _cls: &Bound<'_, pyo3::types::PyType>,
        py: Python<'_>,
        parts: Vec<Py<NamePart>>,
    ) -> Vec<Py<NamePart>> {
        tag_sort_parts(py, parts)
    }
}

/// Rust-callable version of [`NamePart::tag_sort`]. Shared by the
/// classmethod and by [`crate::names::alignment`]'s fallback path.
///
/// **Stable**: parts with the same tag preserve their input order.
/// Relied on by the alignment fallback path, which depends on the
/// output being deterministic for a given input sequence.
pub fn tag_sort_parts(py: Python<'_>, parts: Vec<Py<NamePart>>) -> Vec<Py<NamePart>> {
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

impl NamePart {
    /// Rust-only accessor for the token text. Cheaper than
    /// `self.form.bind(py).extract::<String>()` when you already hold
    /// a `&NamePart`.
    pub fn form_str(&self) -> &str {
        &self.form_str
    }

    /// Rust-only accessor for the cached comparable form. Hot-path
    /// win when the analyze / contains pipelines walk parts and
    /// read `.comparable` per part — avoids a per-iteration
    /// `PyString` extract.
    pub fn comparable_str(&self) -> &str {
        &self.comparable_str
    }

    /// Rust-only accessor for the cached hash. Used for part-identity
    /// tracking in the analyze pipeline.
    pub fn hash_isize(&self) -> isize {
        self.hash
    }
}

fn hash_namepart(index: u32, form: &str) -> isize {
    let mut hasher = DefaultHasher::new();
    index.hash(&mut hasher);
    form.hash(&mut hasher);
    hasher.finish() as isize
}

/// A contiguous group of [`NamePart`]s annotated with a
/// [`crate::names::symbol::Symbol`] — the tagger's output unit.
#[pyclass(module = "rigour._core")]
pub struct Span {
    /// The [`NamePart`]s covered by this span. Same `Py<NamePart>`
    /// references that live in the parent [`crate::names::name::Name`]'s
    /// `.parts`, so `span.parts[0] is name.parts[i]` is `True` from
    /// Python. Exposed as a tuple — hashable, so downstream code can
    /// key on `(span.parts, span.symbol.category)` when deduplicating
    /// pairings.
    #[pyo3(get)]
    pub parts: Py<pyo3::types::PyTuple>,
    /// The symbol this span carries.
    #[pyo3(get)]
    pub symbol: Py<crate::names::symbol::Symbol>,
    /// Space-joined `part.comparable` over the covered parts, for
    /// use in matcher-side substring checks.
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
            segments.push(part.comparable_str().to_string());
            len_chars += part.form_str.chars().count();
        }
        let comparable_str = segments.join(" ");
        let comparable_py = PyString::new(py, &comparable_str).unbind();

        let hash = hash_span(py, &parts, &symbol);
        let parts_list = pyo3::types::PyTuple::new(py, &parts)?.unbind();

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
