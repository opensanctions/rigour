//! [`Symbol`] — a semantic annotation the tagger attaches to one or
//! more parts of a [`crate::names::name::Name`].

#[cfg(feature = "python")]
use pyo3::exceptions::PyTypeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, LazyLock, RwLock};

/// The kind of semantic annotation a [`Symbol`] carries. Scorers
/// weight matches by category: `ORG_CLASS` is strong evidence,
/// `INITIAL` needs token-level corroboration.
// SCREAMING_SNAKE_CASE variants give the Python attribute names
// directly; `#[pyo3(name = …)]` renames don't work under `cfg_attr`.
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
    /// First letter of a latin name part (`j` for "John").
    INITIAL,
    /// Known personal name; id is a Wikidata QID (`Q4925477`) or an
    /// `X`-prefixed manual id.
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
    /// Return the stable short key used in serialised symbols (e.g.
    /// yente's `f"{category.value}:{id}"` index field). Changing these
    /// strings breaks existing indexes.
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

/// Return a process-wide shared `Arc<str>` for `s`.
///
/// Entries are never evicted, so only intern strings from a bounded
/// vocabulary.
pub fn intern(s: &str) -> Arc<str> {
    if let Some(a) = INTERNER.read().unwrap().get(s) {
        return a.clone();
    }
    // Another thread may have inserted between the read and write locks.
    let mut w = INTERNER.write().unwrap();
    if let Some(a) = w.get(s) {
        return a.clone();
    }
    let arc: Arc<str> = Arc::from(s);
    w.insert(arc.as_ref().into(), arc.clone());
    arc
}

/// A semantic annotation on one or more parts of a name, compared
/// between names as match evidence and flattened into search indexes.
///
/// Ids are always strings; integer ids are stored in decimal form, so
/// `(NUMERIC, 5)` and `(NUMERIC, "5")` are the same symbol.
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
    /// Build a `Symbol` from an integer id.
    pub fn from_u32(category: SymbolCategory, n: u32) -> Self {
        Self::from_str(category, &n.to_string())
    }

    /// Build a `Symbol` from a wide integer id, such as a 13-digit
    /// registry number parsed from a name part.
    pub fn from_i64(category: SymbolCategory, n: i64) -> Self {
        Self::from_str(category, &n.to_string())
    }

    /// Build a `Symbol` from a string id.
    pub fn from_str(category: SymbolCategory, s: &str) -> Self {
        Symbol {
            category,
            // Numeric ids come from arbitrary input text; interning them
            // would retain every distinct number for the process lifetime.
            id: if category == SymbolCategory::NUMERIC {
                Arc::from(s)
            } else {
                intern(s)
            },
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl Symbol {
    /// Construct a `Symbol`; `Symbol(cat, 5)` equals `Symbol(cat, "5")`.
    ///
    /// Args:
    ///     category: Kind of semantic annotation.
    ///     id: String or integer identifier within the category.
    #[new]
    fn py_new(category: SymbolCategory, id: &Bound<'_, PyAny>) -> PyResult<Self> {
        if let Ok(s) = id.extract::<&str>() {
            Ok(Self::from_str(category, s))
        } else if let Ok(n) = id.extract::<i64>() {
            Ok(Self::from_i64(category, n))
        } else {
            Err(PyTypeError::new_err("Symbol id must be str or int"))
        }
    }

    #[getter]
    fn category(&self) -> SymbolCategory {
        self.category
    }

    /// The id string; integer ids come back in decimal form.
    #[getter]
    fn id(&self) -> &str {
        &self.id
    }

    /// Compact form for logs, e.g. `[ORGCLS:LLC]`.
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
        assert!(Arc::ptr_eq(&a.id, &b.id));
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
    fn numeric_ids_bypass_interner() {
        let a = Symbol::from_i64(SymbolCategory::NUMERIC, 5077746887312);
        let id = Arc::downgrade(&a.id);
        drop(a);
        assert!(id.upgrade().is_none());
    }

    #[test]
    fn int_and_str_constructors_converge() {
        let a = Symbol::from_u32(SymbolCategory::NUMERIC, 5);
        let b = Symbol::from_str(SymbolCategory::NUMERIC, "5");
        let c = Symbol::from_i64(SymbolCategory::NUMERIC, 5);
        assert_eq!(a, b);
        assert_eq!(a, c);
    }

    #[test]
    fn from_i64_preserves_wide_values() {
        // Truncating to u32 would collide distinct registry numbers.
        let a = Symbol::from_i64(SymbolCategory::NUMERIC, 5077746887312);
        assert_eq!(a.id.as_ref(), "5077746887312");
        let b = Symbol::from_str(SymbolCategory::NUMERIC, "5077746887312");
        assert_eq!(a, b);
    }

    #[test]
    fn category_values_are_stable() {
        // Downstream consumers (yente's index_symbol, log output)
        // depend on these exact strings.
        assert_eq!(SymbolCategory::ORG_CLASS.value(), "ORGCLS");
        assert_eq!(SymbolCategory::NUMERIC.value(), "NUM");
        assert_eq!(SymbolCategory::LOCATION.value(), "LOC");
        assert_eq!(SymbolCategory::PHONETIC.value(), "PHON");
    }
}
