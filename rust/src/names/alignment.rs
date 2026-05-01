//! The [`Alignment`] pyclass — one piece of name-comparison
//! evidence. Returned by both [`pair_symbols`] (with a `Symbol`)
//! and [`compare_parts`] (without). Fully immutable post-
//! construction; precomputes `qstr` / `rstr` from the parts'
//! comparable forms for cheap rendering and literal-equality
//! checks.
//!
//! [`pair_symbols`]: super::pairing::py_pair_symbols
//! [`compare_parts`]: super::compare::py_compare_parts

use std::hash::{DefaultHasher, Hash, Hasher};

use pyo3::prelude::*;
use pyo3::types::{PyString, PyTuple};

use crate::names::part::NamePart;
use crate::names::symbol::Symbol;

/// One unit of name-comparison evidence.
///
/// Three modes:
///
/// - **Symbol-paired edge** — `symbol` is `Some` and both sides
///   carry the same `Symbol`. Returned by `pair_symbols`. Default
///   `score` is `1.0`; consumers may override with a category
///   default (e.g. `SYM_SCORES[NAME] = 0.9`).
/// - **Residue cluster** — `symbol` is `None`, both sides
///   non-empty. Returned by `compare_parts` for parts that
///   aligned by edit distance.
/// - **Extra** — `symbol` is `None`, exactly one side is empty.
///   Represents a part that found no counterpart on the other
///   side; the matcher applies a side-specific weight.
///
/// `qstr` / `rstr` are the space-joined `comparable` forms of
/// each side, precomputed at construction. `__hash__` and
/// `__eq__` key on `(symbol, qps, rps)` — `NamePart` already
/// hashes by `(index, form)`, so position is preserved.
#[pyclass(module = "rigour._core", frozen)]
pub struct Alignment {
    /// Query-side parts covered by this alignment.
    #[pyo3(get)]
    pub qps: Py<PyTuple>,
    /// Result-side parts covered by this alignment.
    #[pyo3(get)]
    pub rps: Py<PyTuple>,
    /// Shared `Symbol` for symbol-paired edges; `None` for
    /// residue clusters and extras.
    #[pyo3(get)]
    pub symbol: Option<Py<Symbol>>,
    /// Similarity in `[0, 1]`. For symbol-paired edges, defaults
    /// to `1.0`; consumers may override with a category default.
    /// For residue clusters, the per-cluster product. For extras,
    /// `0.0`.
    #[pyo3(get)]
    pub score: f64,
    /// `" ".join(p.comparable for p in qps)`, cached.
    #[pyo3(get)]
    pub qstr: Py<PyString>,
    /// `" ".join(p.comparable for p in rps)`, cached.
    #[pyo3(get)]
    pub rstr: Py<PyString>,
    hash: isize,
}

impl Alignment {
    /// Rust-internal builder. Use this from PyO3 entry points
    /// (`pair_symbols`, `compare_parts`) where the parts are
    /// already in hand as `Vec<Py<NamePart>>`.
    pub fn build(
        py: Python<'_>,
        qps: Vec<Py<NamePart>>,
        rps: Vec<Py<NamePart>>,
        symbol: Option<Py<Symbol>>,
        score: f64,
    ) -> PyResult<Self> {
        let mut q_segs: Vec<String> = Vec::with_capacity(qps.len());
        for p in &qps {
            q_segs.push(p.bind(py).borrow().comparable_str().to_string());
        }
        let mut r_segs: Vec<String> = Vec::with_capacity(rps.len());
        for p in &rps {
            r_segs.push(p.bind(py).borrow().comparable_str().to_string());
        }
        let qstr_s = q_segs.join(" ");
        let rstr_s = r_segs.join(" ");

        let mut h = DefaultHasher::new();
        match &symbol {
            Some(s) => {
                let sym = s.bind(py).borrow();
                sym.category.hash(&mut h);
                sym.id.hash(&mut h);
            }
            None => 0u8.hash(&mut h),
        }
        for p in &qps {
            p.bind(py).borrow().hash_isize().hash(&mut h);
        }
        // Separator between sides so (q=[a], r=[]) and (q=[], r=[a]) hash differently.
        u32::MAX.hash(&mut h);
        for p in &rps {
            p.bind(py).borrow().hash_isize().hash(&mut h);
        }
        let hash = h.finish() as isize;

        let qps_tuple = PyTuple::new(py, &qps)?.unbind();
        let rps_tuple = PyTuple::new(py, &rps)?.unbind();

        Ok(Self {
            qps: qps_tuple,
            rps: rps_tuple,
            symbol,
            score,
            qstr: PyString::new(py, &qstr_s).unbind(),
            rstr: PyString::new(py, &rstr_s).unbind(),
            hash,
        })
    }
}

#[pymethods]
impl Alignment {
    /// Construct an `Alignment`.
    ///
    /// `qps` / `rps` are sequences of `NamePart`. `symbol` is the
    /// shared `Symbol` for symbol-paired edges, `None` otherwise.
    /// `score` defaults to `0.0`.
    ///
    /// `qstr` / `rstr` are derived from `part.comparable` and
    /// cached at construction.
    #[new]
    #[pyo3(signature = (qps, rps, symbol = None, score = 0.0))]
    pub fn new(
        py: Python<'_>,
        qps: Vec<Py<NamePart>>,
        rps: Vec<Py<NamePart>>,
        symbol: Option<Py<Symbol>>,
        score: f64,
    ) -> PyResult<Self> {
        Alignment::build(py, qps, rps, symbol, score)
    }

    fn __hash__(&self) -> isize {
        self.hash
    }

    fn __eq__(&self, py: Python<'_>, other: &Bound<'_, PyAny>) -> PyResult<bool> {
        let Ok(o) = other.extract::<PyRef<'_, Alignment>>() else {
            return Ok(false);
        };
        if self.hash != o.hash {
            return Ok(false);
        }
        let symbols_equal = match (&self.symbol, &o.symbol) {
            (None, None) => true,
            (Some(a), Some(b)) => *a.bind(py).borrow() == *b.bind(py).borrow(),
            _ => false,
        };
        if !symbols_equal {
            return Ok(false);
        }
        let q_eq = self.qps.bind(py).eq(o.qps.bind(py))?;
        if !q_eq {
            return Ok(false);
        }
        self.rps.bind(py).eq(o.rps.bind(py))
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        let qstr: String = self.qstr.bind(py).extract()?;
        let rstr: String = self.rstr.bind(py).extract()?;
        let sym_str = match &self.symbol {
            Some(s) => {
                let sym = s.bind(py).borrow();
                format!("{}:{}", sym.category.value(), sym.id)
            }
            None => "None".to_string(),
        };
        Ok(format!(
            "<Alignment(qps={qstr:?}, rps={rstr:?}, symbol={sym_str}, score={:.4})>",
            self.score
        ))
    }
}
