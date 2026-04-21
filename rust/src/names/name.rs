//! The [`Name`] pyclass — the entry point to the rigour names
//! object graph. A `Name` wraps the original input string alongside
//! a tokenised list of [`NamePart`]s and any [`Span`]s the tagger
//! has attached.

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

/// A personal, organisational, or object name.
///
/// Exposed attributes:
///
/// | field | type | notes |
/// |---|---|---|
/// | `original` | `str` | input string, verbatim |
/// | `form` | `str` | normalised form (casefolded by default) |
/// | `tag` | [`NameTypeTag`] | mutable |
/// | `lang` | `str \| None` | optional language hint, mutable |
/// | `parts` | `list[NamePart]` | tokens of `form` |
/// | `spans` | `list[Span]` | tagger output — grows via `apply_phrase` / `apply_part` |
/// | `comparable` | `str` | space-joined `part.comparable`, precomputed |
/// | `norm_form` | `str` | space-joined `part.form`, precomputed |
/// | `symbols` | `set[Symbol]` | dynamic — rebuilt from `spans` on each access |
///
/// Equality and hashing are over `form`. A `Name`'s `tag` and `lang`
/// can change, and `spans` grows, without affecting hash or equality.
#[pyclass(module = "rigour._core")]
pub struct Name {
    #[pyo3(get)]
    pub original: Py<PyString>,
    #[pyo3(get)]
    pub form: Py<PyString>,
    #[pyo3(get, set)]
    pub tag: NameTypeTag,
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
    /// Args:
    ///   * `original` — the raw input string.
    ///   * `form` — a pre-normalised form. If omitted, the
    ///     constructor casefolds `original` and uses that.
    ///   * `tag` — initial [`NameTypeTag`], defaulting to `UNK`.
    ///   * `lang` — optional ISO language hint.
    ///   * `parts` — pre-tokenised [`NamePart`]s. If omitted, the
    ///     constructor tokenises `form` and builds one `NamePart`
    ///     per token.
    ///   * `phonetics` — forwarded to each constructed `NamePart`;
    ///     when `false`, skips metaphone computation. Ignored when
    ///     `parts` is supplied.
    ///
    /// `comparable` and `norm_form` are computed eagerly from the
    /// parts and cached. `spans` starts empty.
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
                        NamePart::new(py, &token, Some(i as u32), NamePartTag::UNSET, phonetics);
                    let part_py = Py::new(py, part)?;
                    built.push(part_py);
                }
                let list = PyList::new(py, &built)?.unbind();
                (built, list)
            }
        };

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

    /// Tag the parts that spell out `text` with the given tag.
    ///
    /// Used when external metadata tells the caller the structural
    /// role of a subset of the name's tokens. For example, an FTM
    /// `firstName` property of "Jean Claude" on a name "Jean Claude
    /// Juncker" marks both the `jean` and `claude` parts as
    /// `GIVEN`; a `lastName` of "Juncker" then marks the remaining
    /// part as `FAMILY`.
    ///
    /// Walks `self.parts` looking for a contiguous
    /// (adjacency-insensitive) match of the tokenised `text`. On a
    /// hit, each matched part's tag is set to `tag`; parts that
    /// already carry a tag that conflicts under
    /// [`NamePartTag::can_match`] demote to `AMBIGUOUS` instead.
    /// Stops after `max_matches` successful matches.
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

    /// Record that `phrase` in this name carries `symbol`.
    ///
    /// The tagger's output path: when the AC automaton reports a
    /// recognised phrase (e.g. "limited liability company" →
    /// `ORG_CLASS:LLP`), the match is attached as a [`Span`] so
    /// downstream matching and inference can see which tokens the
    /// symbol covers. Every non-overlapping occurrence of `phrase`
    /// in the name gets its own `Span`.
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
                let span = Span::new(py, span_parts, symbol.clone_ref(py))?;
                let span_py = Py::new(py, span)?;
                spans_bound.append(span_py)?;
                matching.clear();
            }
        }
        Ok(())
    }

    /// Record that a single [`NamePart`] carries `symbol`.
    ///
    /// The single-part variant of [`Name::apply_phrase`]. Used for
    /// symbols that inherently apply to one token: `INITIAL` on a
    /// single-character latin part, `NUMERIC` inferred from a part
    /// like "123456789" that the ordinal tagger didn't cover.
    pub fn apply_part(
        &self,
        py: Python<'_>,
        part: Py<NamePart>,
        symbol: Py<Symbol>,
    ) -> PyResult<()> {
        let span = Span::new(py, vec![part], symbol)?;
        let span_py = Py::new(py, span)?;
        self.spans.bind(py).append(span_py)?;
        Ok(())
    }

    /// Aggregate view of every symbol the tagger has attached to
    /// this name. Useful when you want the symbol set regardless of
    /// which parts carry them (e.g. indexing the name's semantic
    /// annotations into a flat field).
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

    /// `True` iff this name structurally contains `other`.
    ///
    /// Used by matcher pipelines to detect when one name's evidence
    /// is a subset of another's — e.g. "John Smith" is contained in
    /// "John K Smith", and the longer form supersedes the shorter
    /// when consolidating candidate names before scoring
    /// (see [`Name::consolidate_names`]). Also backs middle-initial
    /// matching: "John Smith" contains "J. Smith" when the `J`
    /// carries an `INITIAL` symbol that `self` also has.
    ///
    /// Rule: for PER names, every part of `other` must have a
    /// (not-necessarily-adjacent) comparable-equal counterpart in
    /// `self`. For non-PER names, or when the PER rule doesn't find
    /// a full subset, falls back to substring containment of
    /// `norm_form`. Returns `False` when `self.tag == UNK` or when
    /// the two names are equal.
    pub fn contains(&self, py: Python<'_>, other: PyRef<'_, Name>) -> PyResult<bool> {
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

    /// Drop short names that are contained in longer names.
    ///
    /// Useful when building a matcher to prevent a scenario where a
    /// short version of a name ("John Smith") is matched against a
    /// query "John K Smith" — where the longer candidate version
    /// would have correctly disqualified the match
    /// ("John K Smith" != "John R Smith"). Keeping only the longer
    /// form forces the matcher to reckon with the full evidence.
    ///
    /// Containment uses [`Name::contains`]; see there for the
    /// PER-aware subset rule. Accepts any Python iterable of `Name`;
    /// returns a new set.
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

/// Multi-set intersection: each element in `a` consumes at most one
/// matching element in `b`; the matched elements form the output.
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
    let mut hasher = DefaultHasher::new();
    form.hash(&mut hasher);
    hasher.finish() as isize
}
