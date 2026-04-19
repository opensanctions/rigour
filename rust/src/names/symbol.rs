// Compact `Symbol` representation backed by an `Arc<str>` id and a
// global string interner. See `plans/rust-symbols.md` for the design
// rationale — briefly:
//
//   - 24-byte struct (1 B category + 7 B pad + 16 B Arc<str>).
//   - Id is always a string; integer-source ids (ordinals, Wikidata
//     Q-numbers) are stringified at construction.
//   - All distinct id strings go through `intern()` — one heap
//     allocation per distinct string, shared via `Arc<str>` refcount.
//     Symbols built from the same logical id share one allocation.
//   - `SymbolCategory` is a sealed `#[pyclass]` enum exposed to Python
//     with the pre-port ALL_CAPS variant names and `.value` strings.
//
// PyO3 attributes are gated behind the `python` feature so `cargo
// test` and pure-Rust consumers still compile; the inherent impls
// with `value()` etc. are always available.

#[cfg(feature = "python")]
use pyo3::exceptions::PyTypeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::{Arc, LazyLock, RwLock};

/// Sealed enum of symbol categories — the full set is fixed at
/// compile time and adding a variant is a cross-stack data-model
/// change. Rust `match` exhaustiveness catches missed cases at
/// compile time; Python gets the same semantic protection at
/// import time via the finite `SymbolCategory.<variant>` attribute set.
// Variants use SCREAMING_SNAKE_CASE to match the Python enum's
// attribute names exactly, without needing `#[pyo3(name = ...)]`
// renames (those helper attributes don't play well with cfg_attr
// gating). The non-idiomatic style is scoped to this one enum.
#[allow(non_camel_case_types)]
#[cfg_attr(
    feature = "python",
    pyclass(eq, hash, frozen, from_py_object, module = "rigour._core")
)]
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash)]
pub enum SymbolCategory {
    ORG_CLASS,
    SYMBOL,
    DOMAIN,
    INITIAL,
    NAME,
    NICK,
    NUMERIC,
    LOCATION,
    PHONETIC,
}

impl SymbolCategory {
    /// The short serialisation key for this category (e.g.
    /// `"ORGCLS"`, `"NUM"`). Used downstream in yente's
    /// `index_symbol` and anywhere else a categorical discriminator
    /// needs a stable string form. Matches the pre-port Python enum's
    /// `.value`, which downstream code relies on.
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

// Global string interner. Read-mostly after warmup: tagger-build
// passes populate most entries once, subsequent Symbol construction
// (from ad-hoc Python code or from matching-loop results) hits the
// read lock. Never shrinks — entries live for the process lifetime,
// which is fine given the bounded set of distinct ids in the data
// model. See `plans/rust-symbols.md` for the size budget.
type Interner = RwLock<HashMap<Box<str>, Arc<str>>>;
static INTERNER: LazyLock<Interner> = LazyLock::new(|| RwLock::new(HashMap::new()));

/// Return the canonical `Arc<str>` for `s`. Two calls with equal
/// input return clones of the same `Arc`, so `Arc::ptr_eq` is a
/// valid fast path for equality.
pub fn intern(s: &str) -> Arc<str> {
    // Fast path: read lock — the common case after warmup.
    if let Some(a) = INTERNER.read().unwrap().get(s) {
        return a.clone();
    }
    // Slow path: upgrade to write lock and double-check. Another
    // thread may have inserted between read-release and write-
    // acquire; we check before creating a fresh Arc.
    let mut w = INTERNER.write().unwrap();
    if let Some(a) = w.get(s) {
        return a.clone();
    }
    let arc: Arc<str> = Arc::from(s);
    w.insert(arc.as_ref().into(), arc.clone());
    arc
}

/// Semantic interpretation applied to one or more parts of a name.
/// Holds a category discriminator plus an id that's always a string
/// (integer-sourced ids like Wikidata QIDs or ordinal numbers get
/// stringified at construction). Equality and hashing are structural
/// over `(category, id)`; frozen to satisfy `pyclass(hash)`.
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
    /// Rust-side convenience constructor: stringifies `n` and interns.
    /// Used by data-load paths that source ids as integers (ordinals,
    /// Wikidata Q-numbers, initial codepoints).
    pub fn from_u32(category: SymbolCategory, n: u32) -> Self {
        Symbol {
            category,
            id: intern(&n.to_string()),
        }
    }

    /// Rust-side convenience constructor from a `&str`.
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
    /// Accepts `id` as `str` or `int` — ints are decimal-stringified.
    /// Both go through the interner, so `Symbol(cat, 5)` and
    /// `Symbol(cat, "5")` are equal (and share one `Arc<str>`).
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

    /// The interned id string. Always `str` on the Python side; ids
    /// originally passed as `int` are returned as their decimal form.
    #[getter]
    fn id(&self) -> &str {
        &self.id
    }

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
        // Symbol::from_u32(NUMERIC, 5) and Symbol::from_str(NUMERIC, "5")
        // should produce equal Symbols — the interner deduplicates
        // independent of construction path.
        let a = Symbol::from_u32(SymbolCategory::NUMERIC, 5);
        let b = Symbol::from_str(SymbolCategory::NUMERIC, "5");
        assert_eq!(a, b);
        assert!(Arc::ptr_eq(&a.id, &b.id));
    }

    #[test]
    fn category_value_preserves_pre_port_strings() {
        // yente's index_symbol and anything else reading `.value`
        // depends on these exact strings.
        assert_eq!(SymbolCategory::ORG_CLASS.value(), "ORGCLS");
        assert_eq!(SymbolCategory::NUMERIC.value(), "NUM");
        assert_eq!(SymbolCategory::LOCATION.value(), "LOC");
        assert_eq!(SymbolCategory::PHONETIC.value(), "PHON");
    }
}
