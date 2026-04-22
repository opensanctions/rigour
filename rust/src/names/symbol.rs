//! [`Symbol`] — a semantic annotation the tagger attaches to one or
//! more parts of a [`crate::names::name::Name`].

#[cfg(feature = "python")]
use pyo3::exceptions::PyTypeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, LazyLock, RwLock};

/// The kind of semantic annotation a [`Symbol`] carries. Drives how
/// strongly a symbol match counts during scoring — an `ORG_CLASS`
/// match is a strong corporate-form signal, an `INITIAL` match is
/// weak evidence that needs token-level corroboration.
// Variants use SCREAMING_SNAKE_CASE so the Python-facing attribute
// names (via `#[pyclass]`) match without individual `#[pyo3(name = …)]`
// renames; the latter don't play well with `cfg_attr` gating.
#[allow(non_camel_case_types)]
#[cfg_attr(
    feature = "python",
    pyclass(eq, hash, frozen, from_py_object, module = "rigour._core")
)]
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum SymbolCategory {
    /// Legal-form class abbreviation (LLC, GmbH, AG, …).
    ORG_CLASS,
    /// Generic organisational qualifier keyword (e.g. `INDUSTRY`,
    /// `FINANCE`, `HOLDING`).
    SYMBOL,
    /// Industry or sector domain (e.g. `ENERGY`, `BANKING`).
    DOMAIN,
    /// Single-letter initial standing in for a given name (`j` for
    /// "John"); attached to single-character latin name parts.
    INITIAL,
    /// A known personal name from the reference corpus; id is the
    /// Wikidata QID (e.g. `Q4925477` for "John") or an `X`-prefixed
    /// manual-override id.
    NAME,
    /// Nickname or weak alias attached to a name part.
    NICK,
    /// Integer-valued parse of a numeric part (e.g. `"1984"`).
    NUMERIC,
    /// Place reference (territory code).
    LOCATION,
    /// Phonetic bucket key used for fuzzy grouping across names.
    PHONETIC,
}

impl SymbolCategory {
    /// Short stable key used for downstream serialisation — yente's
    /// flat symbol index field uses `f"{category.value}:{id}"`, for
    /// example, and logs / exports expect the same strings.
    pub fn value(&self) -> &'static str {
        match self {
            SymbolCategory::ORG_CLASS => "ORGCLS",
            SymbolCategory::SYMBOL => "SYMBOL",
            SymbolCategory::DOMAIN => "DOMAIN",
            SymbolCategory::INITIAL => "INITIAL",
            SymbolCategory::NAME => "NAME",
            SymbolCategory::NICK => "NICK",
            SymbolCategory::NUMERIC => "NUM",
            SymbolCategory::LOCATION => "LOC",
            SymbolCategory::PHONETIC => "PHON",
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl SymbolCategory {
    #[getter(value)]
    fn py_value(&self) -> &'static str {
        self.value()
    }
}

type Interner = RwLock<HashMap<Box<str>, Arc<str>>>;
static INTERNER: LazyLock<Interner> = LazyLock::new(|| RwLock::new(HashMap::new()));

/// Dedup id strings across the process so that logically-equal
/// symbols share one heap allocation.
///
/// Tagger runs emit millions of [`Symbol`]s over a small set of
/// distinct ids (a few thousand Wikidata QIDs, the LLC/GmbH/etc.
/// vocabulary, territory codes). Sharing an `Arc<str>` per distinct
/// id keeps the working set in the low MBs instead of the GBs a
/// naïve `String`-per-symbol layout would take. The interner never
/// shrinks — entries live for the process lifetime, which is fine
/// given the bounded set.
pub fn intern(s: &str) -> Arc<str> {
    // Fast path: read lock — the common case after the tagger has
    // populated the interner on first use.
    if let Some(a) = INTERNER.read().unwrap().get(s) {
        return a.clone();
    }
    // Slow path: another thread may have inserted between
    // read-release and write-acquire, so check again before creating
    // a fresh `Arc`.
    let mut w = INTERNER.write().unwrap();
    if let Some(a) = w.get(s) {
        return a.clone();
    }
    let arc: Arc<str> = Arc::from(s);
    w.insert(arc.as_ref().into(), arc.clone());
    arc
}

/// A semantic interpretation applied to one or more parts of a name.
///
/// Carries a [`SymbolCategory`] and an id. Tagger pipelines emit
/// Symbols during name analysis; matchers compare them between
/// names as a coarse compatibility signal, and indexers flatten
/// them into searchable fields. Equality and hashing are
/// structural over `(category, id)`.
///
/// Ids are always `str` — integer-sourced ids (Wikidata QIDs,
/// ordinals, initial codepoints) are decimal-stringified at
/// construction. Distinct `Symbol`s with equal ids share one
/// [`Arc<str>`] heap allocation via [`intern`].
#[cfg_attr(
    feature = "python",
    pyclass(eq, hash, frozen, from_py_object, module = "rigour._core")
)]
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Symbol {
    pub category: SymbolCategory,
    pub id: Arc<str>,
}

impl Symbol {
    /// Build a `Symbol` from an integer id. Used by data-load paths
    /// that source ids as integers (Wikidata Q-numbers, ordinals,
    /// `INITIAL` codepoints). The integer is decimal-stringified and
    /// interned, so `Symbol::from_u32(NUMERIC, 5)` and
    /// `Symbol::from_str(NUMERIC, "5")` are equal and share one
    /// allocation.
    pub fn from_u32(category: SymbolCategory, n: u32) -> Self {
        Symbol {
            category,
            id: intern(&n.to_string()),
        }
    }

    /// Build a `Symbol` from a string id. Used by the tagger when
    /// attaching symbols with text-shaped ids (`ORG_CLASS:LLC`,
    /// territory codes, Wikidata QIDs with the `Q` prefix).
    pub fn from_str(category: SymbolCategory, s: &str) -> Self {
        Symbol {
            category,
            id: intern(s),
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl Symbol {
    /// Construct a `Symbol` from Python. `id` accepts `str` or
    /// `int`; integer ids are decimal-stringified and interned, so
    /// `Symbol(cat, 5)` and `Symbol(cat, "5")` compare equal and
    /// share one heap allocation.
    #[new]
    fn py_new(category: SymbolCategory, id: &Bound<'_, PyAny>) -> PyResult<Self> {
        let id_arc = if let Ok(s) = id.extract::<&str>() {
            intern(s)
        } else if let Ok(n) = id.extract::<i64>() {
            intern(&n.to_string())
        } else {
            return Err(PyTypeError::new_err("Symbol id must be str or int"));
        };
        Ok(Symbol {
            category,
            id: id_arc,
        })
    }

    #[getter]
    fn category(&self) -> SymbolCategory {
        self.category
    }

    /// The interned id string. Always `str` on the Python side —
    /// ids originally passed as `int` return as their decimal form.
    #[getter]
    fn id(&self) -> &str {
        &self.id
    }

    /// Compact human-readable form used in logs and debug output,
    /// e.g. `[ORGCLS:LLC]`.
    fn __str__(&self) -> String {
        format!("[{}:{}]", self.category.value(), self.id)
    }

    fn __repr__(&self) -> String {
        format!("<Symbol({:?}, {})>", self.category, self.id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn intern_returns_same_arc_for_equal_inputs() {
        let a = intern("foo");
        let b = intern("foo");
        assert!(
            Arc::ptr_eq(&a, &b),
            "interner must return the same Arc for equal inputs"
        );
    }

    #[test]
    fn intern_distinct_inputs_give_distinct_arcs() {
        let a = intern("foo");
        let b = intern("bar");
        assert!(!Arc::ptr_eq(&a, &b));
        assert_ne!(a.as_ref(), b.as_ref());
    }

    #[test]
    fn symbols_equal_by_category_and_id() {
        let a = Symbol::from_str(SymbolCategory::ORG_CLASS, "LLC");
        let b = Symbol::from_str(SymbolCategory::ORG_CLASS, "LLC");
        assert_eq!(a, b);
    }

    #[test]
    fn symbols_differ_by_category() {
        let a = Symbol::from_str(SymbolCategory::ORG_CLASS, "LLC");
        let b = Symbol::from_str(SymbolCategory::SYMBOL, "LLC");
        assert_ne!(a, b);
    }

    #[test]
    fn symbols_differ_by_id() {
        let a = Symbol::from_str(SymbolCategory::ORG_CLASS, "LLC");
        let b = Symbol::from_str(SymbolCategory::ORG_CLASS, "JSC");
        assert_ne!(a, b);
    }

    #[test]
    fn int_and_str_constructors_converge() {
        let a = Symbol::from_u32(SymbolCategory::NUMERIC, 5);
        let b = Symbol::from_str(SymbolCategory::NUMERIC, "5");
        assert_eq!(a, b);
        assert!(Arc::ptr_eq(&a.id, &b.id));
    }

    #[test]
    fn category_value_preserves_pre_port_strings() {
        // Downstream consumers (yente's index_symbol, log output)
        // depend on these exact strings.
        assert_eq!(SymbolCategory::ORG_CLASS.value(), "ORGCLS");
        assert_eq!(SymbolCategory::NUMERIC.value(), "NUM");
        assert_eq!(SymbolCategory::LOCATION.value(), "LOC");
        assert_eq!(SymbolCategory::PHONETIC.value(), "PHON");
    }
}
