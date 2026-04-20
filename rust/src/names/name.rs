// Rust-backed `Name` — the top-level name object. Python wrapper at
// `rigour/names/name.py` re-exports from `rigour._core`.
//
// Eager construction pipeline at `Name::new`:
//   1. original (input)
//   2. form (input, default casefold(original))
//   3. tag (input, NameTypeTag, default UNK)
//   4. lang (input, Option<str>)
//   5. parts (input or tokenise(form) -> NamePart)
//   6. spans (empty list, grows via apply_phrase/apply_part)
//   7. comparable = " ".join(part.comparable for part in parts)
//   8. norm_form = " ".join(part.form for part in parts)
//   9. hash = hash(form)
//
// `parts` is a `Py<PyList>` of `Py<NamePart>` — built once, stored
// once, returned via INCREF on `.parts` access. `spans` is the same
// shape, but grows over time.
//
// `symbols` is intentionally *not* cached — recomputed each access
// from `spans`. Spans grow via `apply_phrase` / `apply_part`; caching
// would require invalidation.

use std::collections::HashSet;
use std::hash::{DefaultHasher, Hash, Hasher};

use pyo3::prelude::*;
use pyo3::types::{PyList, PyString};

use crate::names::part::{NamePart, Span};
use crate::names::symbol::{Symbol, SymbolCategory};
use crate::names::tag::{NamePartTag, NameTypeTag};
use crate::text::normalize::casefold;
use crate::text::tokenize::tokenize_name;

fn name_tokenize(text: &str) -> Vec<String> {
    tokenize_name(text, 1)
}

/// A name of a thing — person, organisation, object, or unknown.
/// See `rigour/names/name.py` for the Python-side documentation.
#[pyclass(module = "rigour._core")]
pub struct Name {
    #[pyo3(get)]
    pub original: Py<PyString>,
    #[pyo3(get)]
    pub form: Py<PyString>,
    /// Mutable — `_infer_part_tags` can flip ENT→ORG after tagging.
    #[pyo3(get, set)]
    pub tag: NameTypeTag,
    /// Mutable — callers may attach a language hint post-construction.
    #[pyo3(get, set)]
    pub lang: Option<Py<PyString>>,
    #[pyo3(get)]
    pub parts: Py<PyList>,
    #[pyo3(get)]
    pub spans: Py<PyList>,
    #[pyo3(get)]
    pub comparable: Py<PyString>,
    #[pyo3(get)]
    pub norm_form: Py<PyString>,
    form_str: String,
    norm_form_str: String,
    hash: isize,
}

#[pymethods]
impl Name {
    /// Construct a `Name`.
    ///
    /// `form` defaults to `casefold(original)`. `tag` defaults to
    /// `NameTypeTag.UNK`. If `parts` is given, it is used as-is;
    /// otherwise `tokenize_name(form)` produces a fresh `NamePart`
    /// per token. `phonetics` is forwarded to each `NamePart`
    /// constructor during tokenisation — ignored when `parts` is
    /// supplied.
    #[new]
    #[pyo3(signature = (original, form = None, tag = NameTypeTag::UNK, lang = None, parts = None, phonetics = true))]
    pub fn new(
        py: Python<'_>,
        original: &str,
        form: Option<&str>,
        tag: NameTypeTag,
        lang: Option<&str>,
        parts: Option<Vec<Py<NamePart>>>,
        phonetics: bool,
    ) -> PyResult<Self> {
        let form_str = match form {
            Some(f) => f.to_string(),
            None => casefold(original),
        };

        let (parts_vec, parts_list): (Vec<Py<NamePart>>, Py<PyList>) = match parts {
            Some(given) => {
                let list = PyList::new(py, &given)?.unbind();
                (given, list)
            }
            None => {
                let tokens = name_tokenize(&form_str);
                let mut built: Vec<Py<NamePart>> = Vec::with_capacity(tokens.len());
                for (i, token) in tokens.into_iter().enumerate() {
                    let part =
                        NamePart::build(py, &token, Some(i as u32), NamePartTag::UNSET, phonetics);
                    let part_py = Py::new(py, part)?;
                    built.push(part_py);
                }
                let list = PyList::new(py, &built)?.unbind();
                (built, list)
            }
        };

        // Compute comparable and norm_form by folding the parts.
        let mut comparable_segs: Vec<String> = Vec::with_capacity(parts_vec.len());
        let mut norm_segs: Vec<String> = Vec::with_capacity(parts_vec.len());
        for p in &parts_vec {
            let part = p.bind(py).borrow();
            comparable_segs.push(part.comparable.bind(py).extract()?);
            norm_segs.push(part.form_str().to_string());
        }
        let comparable_str = comparable_segs.join(" ");
        let norm_form_str = norm_segs.join(" ");

        let original_py = PyString::new(py, original).unbind();
        let form_py = PyString::new(py, &form_str).unbind();
        let lang_py = lang.map(|l| PyString::new(py, l).unbind());
        let comparable_py = PyString::new(py, &comparable_str).unbind();
        let norm_form_py = PyString::new(py, &norm_form_str).unbind();
        let spans_list = PyList::empty(py).unbind();

        let hash = hash_form(&form_str);

        Ok(Self {
            original: original_py,
            form: form_py,
            tag,
            lang: lang_py,
            parts: parts_list,
            spans: spans_list,
            comparable: comparable_py,
            norm_form: norm_form_py,
            form_str,
            norm_form_str,
            hash,
        })
    }

    /// Tag name parts matching the tokenised form of `text`. See
    /// `rigour/names/name.py::Name.tag_text` for the full semantics.
    #[pyo3(signature = (text, tag, max_matches = 1))]
    pub fn tag_text(
        &self,
        py: Python<'_>,
        text: &str,
        tag: NamePartTag,
        max_matches: u32,
    ) -> PyResult<()> {
        let folded = casefold(text);
        let tokens = name_tokenize(&folded);
        if tokens.is_empty() {
            return Ok(());
        }

        let parts_bound = self.parts.bind(py);
        let mut matches: u32 = 0;
        let mut matching: Vec<Py<NamePart>> = Vec::with_capacity(tokens.len());

        for item in parts_bound.iter() {
            let part_py = item.cast::<NamePart>()?.clone().unbind();
            let next_idx = matching.len();
            let part_form = part_py.bind(py).borrow().form_str().to_string();
            if part_form == tokens[next_idx] {
                matching.push(part_py);
            }
            if matching.len() == tokens.len() {
                apply_tag_to_matching(py, &matching, tag);
                matches += 1;
                if matches >= max_matches {
                    return Ok(());
                }
                matching.clear();
            }
        }
        Ok(())
    }

    /// Apply `symbol` to parts matching the space-separated tokens of
    /// `phrase`. Each non-overlapping match appends a `Span`.
    pub fn apply_phrase(&self, py: Python<'_>, phrase: &str, symbol: Py<Symbol>) -> PyResult<()> {
        let tokens: Vec<&str> = phrase.split(' ').collect();
        if tokens.is_empty() {
            return Ok(());
        }
        let parts_bound = self.parts.bind(py);
        let spans_bound = self.spans.bind(py);
        let mut matching: Vec<Py<NamePart>> = Vec::with_capacity(tokens.len());
        for item in parts_bound.iter() {
            let part_py = item.cast::<NamePart>()?.clone().unbind();
            let next_idx = matching.len();
            let part_form = part_py.bind(py).borrow().form_str().to_string();
            if part_form == tokens[next_idx] {
                matching.push(part_py);
            }
            if matching.len() == tokens.len() {
                let span_parts: Vec<Py<NamePart>> =
                    matching.iter().map(|p| p.clone_ref(py)).collect();
                let span = Span::build(py, span_parts, symbol.clone_ref(py))?;
                let span_py = Py::new(py, span)?;
                spans_bound.append(span_py)?;
                matching.clear();
            }
        }
        Ok(())
    }

    /// Apply `symbol` to a single `NamePart` by appending a `Span`
    /// with just that part.
    pub fn apply_part(
        &self,
        py: Python<'_>,
        part: Py<NamePart>,
        symbol: Py<Symbol>,
    ) -> PyResult<()> {
        let span = Span::build(py, vec![part], symbol)?;
        let span_py = Py::new(py, span)?;
        self.spans.bind(py).append(span_py)?;
        Ok(())
    }

    /// Dynamic `set[Symbol]` aggregated from every span. Recomputed
    /// on each access; intentionally not cached.
    #[getter]
    fn symbols(&self, py: Python<'_>) -> PyResult<Py<pyo3::types::PySet>> {
        let out = pyo3::types::PySet::empty(py)?;
        let spans_bound = self.spans.bind(py);
        for item in spans_bound.iter() {
            let span = item.cast::<Span>()?.borrow();
            out.add(span.symbol.clone_ref(py))?;
        }
        Ok(out.unbind())
    }

    /// `True` iff this name contains `other` under the PER-aware
    /// rules. See Python docstring for details.
    pub fn contains(&self, py: Python<'_>, other: PyRef<'_, Name>) -> PyResult<bool> {
        // Identity short-circuit via form equality.
        if self.form_str == other.form_str {
            return Ok(false);
        }
        if self.tag == NameTypeTag::UNK {
            return Ok(false);
        }
        let self_parts = self.parts.bind(py).len();
        let other_parts = other.parts.bind(py).len();
        if self_parts < other_parts {
            return Ok(false);
        }

        if self.tag == NameTypeTag::PER {
            let self_forms = comparable_list(py, &self.parts)?;
            let other_forms = comparable_list(py, &other.parts)?;
            let mut common = list_intersection(&self_forms, &other_forms);

            // INITIAL-symbol shortcut: if `other` has a single-char
            // INITIAL that matches a symbol in `self`, credit its
            // comparable.
            let other_spans = other.spans.bind(py);
            let self_spans = self.spans.bind(py);
            for o_item in other_spans.iter() {
                let o_span = o_item.cast::<Span>()?.borrow();
                let o_sym = o_span.symbol.bind(py).borrow();
                if o_sym.category != SymbolCategory::INITIAL {
                    continue;
                }
                let o_parts = o_span.parts.bind(py);
                if o_parts.len() == 0 {
                    continue;
                }
                let first_part = o_parts.get_item(0)?.cast::<NamePart>()?.borrow();
                if first_part.form_str().chars().count() > 1 {
                    continue;
                }
                for s_item in self_spans.iter() {
                    let s_span = s_item.cast::<Span>()?.borrow();
                    let s_sym = s_span.symbol.bind(py).borrow();
                    if *o_sym == *s_sym {
                        let o_comp: String = o_span.comparable.bind(py).extract()?;
                        common.push(o_comp);
                        break;
                    }
                }
            }

            if common.len() == other_forms.len() {
                return Ok(true);
            }
        }

        Ok(self.norm_form_str.contains(&other.norm_form_str))
    }

    fn __eq__(&self, other: &Bound<'_, PyAny>) -> bool {
        // `form` is Name's identity — PER/ORG/ENT/OBJ/UNK tags and
        // lang can differ without making two Names "different"
        // (matches the pre-port Python semantics). Extract as Name
        // rather than duck-typing on `.form` attribute.
        match other.extract::<PyRef<'_, Name>>() {
            Ok(n) => n.form_str == self.form_str,
            Err(_) => false,
        }
    }

    fn __hash__(&self) -> isize {
        self.hash
    }

    fn __str__(&self, py: Python<'_>) -> PyResult<String> {
        self.original.bind(py).extract()
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let original: String = self.original.bind(py).extract()?;
        Ok(format!(
            "<Name('{}', '{}', '{}')>",
            original,
            self.form_str,
            self.tag.value(),
        ))
    }

    /// Drop short names that are contained in longer names (PER-aware
    /// rule). Used by the matcher to prevent short-name false-positives.
    /// Accepts any Python iterable of `Name` (set, list, tuple,
    /// generator).
    #[classmethod]
    fn consolidate_names(
        _cls: &Bound<'_, pyo3::types::PyType>,
        py: Python<'_>,
        names: &Bound<'_, PyAny>,
    ) -> PyResult<Py<pyo3::types::PySet>> {
        let iter = names.try_iter()?;
        let mut collected: Vec<Py<Name>> = Vec::new();
        for item in iter {
            let n: Py<Name> = item?.extract()?;
            collected.push(n);
        }
        let mut kept: HashSet<usize> = (0..collected.len()).collect();

        // Replicate itertools.product semantics. O(n^2) as today.
        let len = collected.len();
        for i in 0..len {
            if !kept.contains(&i) {
                continue;
            }
            let name_i = collected[i].bind(py).borrow();
            for (j, candidate) in collected.iter().enumerate() {
                if i == j {
                    continue;
                }
                let name_j = candidate.bind(py).borrow();
                if name_i.contains(py, name_j)? {
                    kept.remove(&j);
                }
            }
        }

        let out = pyo3::types::PySet::empty(py)?;
        for idx in &kept {
            out.add(collected[*idx].clone_ref(py))?;
        }
        Ok(out.unbind())
    }
}

fn apply_tag_to_matching(py: Python<'_>, matching: &[Py<NamePart>], new_tag: NamePartTag) {
    // Mirrors Python logic:
    //   if part.tag == NamePartTag.UNSET: part.tag = new_tag
    //   elif not part.tag.can_match(new_tag): part.tag = AMBIGUOUS
    for part in matching {
        let bind = part.bind(py);
        let current = bind.borrow().tag;
        if current == NamePartTag::UNSET {
            bind.borrow_mut().tag = new_tag;
            continue;
        }
        if !current.can_match(new_tag) {
            bind.borrow_mut().tag = NamePartTag::AMBIGUOUS;
        }
    }
}

fn comparable_list(py: Python<'_>, parts: &Py<PyList>) -> PyResult<Vec<String>> {
    let bound = parts.bind(py);
    let mut out = Vec::with_capacity(bound.len());
    for item in bound.iter() {
        let part = item.cast::<NamePart>()?.borrow();
        let s: String = part.comparable.bind(py).extract()?;
        out.push(s);
    }
    Ok(out)
}

/// Multi-set intersection mirroring `rigour.util.list_intersection`.
/// Each element in `a` that has a matching (not-yet-consumed) element
/// in `b` contributes once to the result.
fn list_intersection(a: &[String], b: &[String]) -> Vec<String> {
    let mut avail: Vec<Option<&String>> = b.iter().map(Some).collect();
    let mut out = Vec::new();
    for x in a {
        for slot in avail.iter_mut() {
            if slot.map(|s| s == x).unwrap_or(false) {
                out.push(x.clone());
                *slot = None;
                break;
            }
        }
    }
    out
}

fn hash_form(form: &str) -> isize {
    // Rust-side SipHash. Python `__hash__` only requires consistency
    // (equal Names hash equal) — which holds because `form` is
    // immutable after Name construction. The specific numeric value
    // is an implementation detail.
    let mut hasher = DefaultHasher::new();
    form.hash(&mut hasher);
    hasher.finish() as isize
}
