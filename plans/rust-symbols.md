---
description: Compact Rust Symbol representation using Arc<str> ids with a global interner, replacing Python's heterogeneous int-or-str id model and supporting the in-progress port of rigour/names/tagging.py
date: 2026-04-19
tags: [rigour, rust, symbols, names, tagging, memory, pyo3]
---

# Rust Symbol: `Arc<str>` ids with a global interner

Companion plan to:
- `plans/rust.md` — umbrella port plan (Phase 4 is the AC tagger that
  produces `Symbol`s).
- `plans/rust-resources.md` — moves `symbols.yml`, `ordinals.yml`, and
  the wordlists under `rust/data/`; this plan picks up where that one
  ends, at `Symbol` construction.
- `plans/rust-names-parser.md` — `Symbol`s are consumed by the
  `analyze_names` pipeline downstream.

## Context

Porting `rigour/names/tagging.py` to Rust means the AC tagger produces
`Symbol` objects in Rust. Today `Symbol` is a Python class with
`__slots__ = ["category", "id"]` and an id that varies by source:

| Source | id type today |
|---|---|
| `ORDINALS` keys | `int` |
| `ORG_SYMBOLS`, `ORG_DOMAINS`, `PERSON_SYMBOLS`, `PERSON_NICK`, `PERSON_NAME_PARTS` YAML keys | `str` (uppercased) |
| `org_types.yml` generic field | `str` (interned) |
| Territory codes (LOCATION) | `str` |
| Part initials | `str` (single char) |
| Person-name corpus (`person_names.txt`) | **mixed** — Wikidata Q-IDs parsed as `int`, XIDs and manual overrides as `str` |

The heterogeneity isn't incidental; it reflects that these ids come
from different sources with different conventions. Attempts to split
by id-type (int vs str) collapse once XIDs and manual overrides enter
the picture — the same conceptual category (`NAME`) legitimately holds
all three id schemes.

Python gets away with this via duck typing and `hash((category, id))`
working for any hashable id. Rust won't — the `Symbol` struct has to
pick one id representation.

Additional constraint: Symbols live in `Name.symbols`, `Span.symbol`,
and the tagger's internal `HashMap<String, Set<Symbol>>` equivalent.
For a nomenklatura index (~200k entities, realistic ~3M Symbol
instances in steady state), the per-Symbol footprint directly drives
whether matching fits comfortably in RAM.

## Decision

```rust
#[pyclass(frozen, hash, eq, module = "rigour._core")]
#[derive(Clone, PartialEq, Eq, Hash, Debug)]
pub struct Symbol {
    category: SymbolCategory,   // #[pyclass] enum, repr(u8), +7 B pad
    id: Arc<str>,               // 16 B (ptr + len); refcount in heap header
}
```

- **Id is always `Arc<str>`**. Numeric-source ids (Wikidata QIDs,
  ordinal numbers) are stringified at construction. Shared storage
  via a global interner makes this cheap.
- **`SymbolCategory`** is a `#[pyclass]`-exposed enum, same variants
  as Python's `Symbol.Category` today (`ORG_CLASS`, `SYMBOL`,
  `DOMAIN`, `INITIAL`, `NAME`, `NICK`, `NUMERIC`, `LOCATION`,
  `PHONETIC`). `repr(u8)` keeps the category field to one byte.
  Sealed: the variant set is fixed data-model — adding one is a
  deliberate change across the stack (rigour + FTM + nomenklatura +
  yente), not an extension point. Rust's exhaustive `match` is load-
  bearing here: any code that renders or weights by category will
  cease to compile if a new variant appears, which is what we want.
- **Python-side `Symbol.id` is always `str`**. Construction accepts
  `str | int` for ergonomics — int gets stringified on the way in.
  This is a breaking change vs. today's Python (where
  `Symbol(NUMERIC, 5).id == 5`); acceptable per the user decision
  in conversation (yente reindexes, downstream updates).

### Why not `u32` + per-category string tables

Considered earlier. Gets to 8 B per Symbol and ~24 MB at 3M Symbols
(vs. ~76 MB with interned Arc). Abandoned because:

1. The heterogeneous id model in `NAME` (QID/XID/manual) requires
   either category splitting (breaks the conceptual bucket) or
   bit-space partitioning (ugly and caps Q-IDs at 2³¹). Both fight
   the reality that these ids really are strings with different
   prefixes.
2. The simplicity cost (tables, reverse lookups, category-aware
   dispatch in `Symbol.id` getter) outweighs the ~50 MB memory
   savings at realistic scale.
3. `Arc<str>` is a familiar Rust idiom with no bespoke machinery —
   any maintainer reads it instantly. The u32-table scheme needs
   explanation every time it's touched.

## Memory footprint

Per-Symbol struct: **24 bytes** (1 B category + 7 B padding +
16 B `Arc<str>`). Heap is shared: one allocation per distinct id,
with a ~16 B Arc header (strong + weak refcount + length prefix).

At realistic tagger scale (3M Symbol instances; 156k unique Wikidata
QIDs in the person-names corpus + ~2k distinct YAML-keyed ids):

| | Count | Per-item | Total |
|---|---|---|---|
| Symbol structs | 3M | 24 B | 72 MB |
| Interner entries | ~158k | ~16 B hdr + avg 8 B str | ~3.8 MB |
| Interner HashMap overhead | ~158k | ~24 B slot + 16 B Box<str> key | ~6 MB |
| **Total** | | | **~82 MB** |

Worst-case (10M Symbols):

| | Total |
|---|---|
| Symbol structs | 240 MB |
| Interner | ~10 MB |
| **Total** | **~250 MB** |

Compared with Python today: ~500–800 MB for the same 3M Symbols
(Symbol object header + id int/str allocations). Compared with
unintern-ed per-Symbol `String`: ~120 MB at 3M (24 B struct + ~8 B
private heap per Symbol). Interning buys ~40 MB back at that scale,
and grows with scale.

## Interner

Global (not per-category) because ids are already disambiguated by
the `(category, id)` pair — a string like `"CO"` appearing as both
`SYMBOL:CO` and `DOMAIN:CO` can legitimately share one `Arc<str>`.

```rust
use std::collections::HashMap;
use std::sync::{Arc, LazyLock, RwLock};

static INTERNER: LazyLock<RwLock<HashMap<Box<str>, Arc<str>>>> =
    LazyLock::new(|| RwLock::new(HashMap::new()));

pub(crate) fn intern(s: &str) -> Arc<str> {
    if let Some(a) = INTERNER.read().unwrap().get(s) {
        return a.clone();
    }
    let mut w = INTERNER.write().unwrap();
    // Re-check under the write lock — someone may have inserted between
    // the read release and the write acquire.
    if let Some(a) = w.get(s) {
        return a.clone();
    }
    let arc: Arc<str> = Arc::from(s);
    w.insert(arc.as_ref().into(), arc.clone());
    arc
}
```

Properties:
- **Read-mostly** after warmup. The tagger-build pass populates most
  strings once; subsequent `Symbol::new` calls from matching or
  Python user code hit the read lock.
- **Never shrinks.** Interned strings live for the process. Fine at
  our scale — ~158k + whatever Python user code constructs; bounded
  by the finite number of distinct ids in the data model.
- **Thread-safe.** The tagger is eventually invoked from Python
  under the GIL, but the interner is written to defensively as if
  no GIL held (cheap enough, and decouples from Python threading
  assumptions for future pure-Rust callers).
- **No category key in the interner.** Interning is just
  string-level deduplication; the Symbol struct carries the category
  separately. A hypothetical future need to track which categories
  an interned string appears in is a separate lookup layer, not part
  of the interner.

No serialisation / cache-clearing. The interner is process-scoped
state, like `LazyLock<Regex>` elsewhere in the crate.

## Equality and hashing

With the interner, **string identity equals `Arc::ptr_eq`**: two
`Arc<str>`s obtained from `intern()` for the same input string point
to the same allocation. So `Symbol::eq` could short-circuit via
pointer comparison on the id.

But: Rust's default `PartialEq` for `Arc<str>` compares contents,
not pointers. We get correct behaviour even if a Symbol is
constructed bypassing the interner (shouldn't happen, but defensive)
— at the cost of a byte compare on every comparison.

**Default plan**: use derived `PartialEq` / `Eq` / `Hash` (content-
comparing). Byte comparison on a small string is ~1–3 ns — still
fast. If profiling ever shows Symbol equality as a hot spot, add a
manual impl that does `Arc::ptr_eq` first and falls through to
content compare. Low-priority optimisation.

Hash: content-hashed via the derived impl. `HashMap<Symbol, _>` and
`HashSet<Symbol>` work as expected.

## Python surface

`rigour.names.symbol` becomes a re-export from the Rust extension.
The class signature matches today's with one change:

```python
# Before (Python, today)
class Symbol:
    class Category(Enum):
        ORG_CLASS = "ORGCLS"
        SYMBOL = "SYMBOL"
        # ...
    def __init__(self, category: Category, id: Any) -> None: ...
    @property
    def id(self) -> Any: ...  # int | str, depending on category

# After (Rust-backed, via PyO3)
class Symbol:
    class Category(Enum):
        ORG_CLASS = "ORGCLS"
        # ... same variants
    def __init__(self, category: Category, id: str | int) -> None:
        """`id` is stringified on construction if passed as int."""
    @property
    def id(self) -> str: ...  # always str
```

`Symbol.id` returning `str` uniformly is the one breaking change.
Call sites that read `symbol.id` as an int today update to compare
against strings:

```python
# Before
if symbol.category == Symbol.Category.NUMERIC and symbol.id == 5:
# After
if symbol.category == Symbol.Category.NUMERIC and symbol.id == "5":
```

`str(symbol.id)` on the old code path returns the same value as
the new `symbol.id` directly — so any call site that already
stringifies (e.g. yente's `index_symbol = f"{cat.value}:{sym.id}"`)
is unaffected.

## Construction paths

1. **From Rust (tagger build)**: direct `Symbol::new(category, id: &str)`
   which calls `intern(id)` and stores the resulting `Arc<str>`.
2. **From Rust with integer-source id** (ordinals, Wikidata QIDs):
   `Symbol::from_int(category, id: u32)` which formats and interns.
   Convenience wrapper around (1).
3. **From Python**: PyO3 `#[new]` accepts `PyAny` for the id arg.
   - `PyString` → `intern(s)`.
   - `PyInt` → format to decimal string, `intern`.
   - Other types → `TypeError`.

All three paths funnel through `intern()`, so the pointer-identity
invariant holds: if you constructed two Symbols with the same
logical id, their `Arc<str>`s are the same allocation.

## Memory of the wider Symbol graph

This plan only sizes the `Symbol` struct. Symbols are embedded in:

- `Span.symbol: Symbol` (owned, one per span).
- `Name.symbols: HashSet<Symbol>` (owned, deduplicated).
- Tagger's `HashMap<String, Set<Symbol>>` equivalent (owned, built at
  tagger-load, held for process life via `LazyLock`).

None of these change the per-Symbol analysis, but they compound:
`Span` gains ~24 B from its owned Symbol (vs. Python pointer-to-
Symbol). If Span ownership becomes a hotspot, a follow-up could
swap to `Arc<Symbol>` or store an index into a Name-local symbol
table. Not in scope here.

## Out of scope / follow-ups

- **`compact_str`-style inline small strings.** CompactString stores
  strings ≤ 24 B inline without heap allocation. Most of our ids
  fit. Gives ~0 heap for short ids at the cost of a 32 B struct vs.
  24 B with Arc<str>. Saves interner state entirely but loses
  sharing for repeated long-ish ids. Memory-wise within ~10% of
  interned Arc at realistic scale; simplicity-wise cleaner
  (no interner). Worth a spike later; interned Arc is the baseline.
- **Category-local interners.** One interner per category rather
  than global. Enables `Symbol::eq` as pure pointer comparison
  without content fallback, since categories partition the id space.
  Slightly more code, slightly less contention on the single global
  `RwLock`. Defer until profiling shows the global interner is a
  bottleneck.
- **Per-process `Symbol` registry**. Assign each distinct
  `(category, id)` pair a dense `u32` id at first construction,
  store the pair in a registry keyed by that u32. Symbol becomes a
  single `u32`. Big memory win at matching-index scale, more
  machinery. Possible end state; not this PR.
- **Splitting `NAME` into semantic sub-categories.** Considered and
  rejected — see Context. If downstream matching ever needs
  different weights for YAML-keyed vs. Wikidata-sourced NAMEs,
  revisit with a plan of its own.

## Verification

- Rust unit tests in `rust/src/names/symbol.rs`:
  - `intern()` returns the same `Arc<str>` for equal inputs.
  - `Symbol::new(cat, "x")` and `Symbol::from_int(cat, 5)` build
    Symbols whose ids are interned.
  - `Symbol` hashes and compares by `(category, id)`.
  - `Symbol` round-trips through PyO3 (construct from Python with
    int and str; read back `symbol.id: str`).
- Python parity tests in `tests/names/test_symbol.py`:
  - Existing Symbol semantics preserved (category equality, hash
    set membership).
  - One new invariant: `Symbol(Category.NUMERIC, 5).id == "5"` —
    pin the breaking change.
- `tests/names/test_tagging.py` updates: call sites comparing
  `symbol.id == <int>` become `symbol.id == <str>`. Mechanical.
- Downstream (nomenklatura `tests/matching/test_symbol_pairings.py`)
  gets updated in the nomenklatura PR that picks up the new
  rigour — out of scope for this plan.

## Files to touch

New:
- `rust/src/names/symbol.rs` — `Symbol` struct, `SymbolCategory`
  enum, `intern()` fn, PyO3 wrappers.

Modified:
- `rust/src/names/mod.rs` — declare the `symbol` module.
- `rust/src/lib.rs` — register `Symbol` and `SymbolCategory` on the
  `PyModule`.
- `rigour/_core.pyi` — add class stubs.
- `rigour/names/symbol.py` — replace the Python class with a
  re-export from `rigour._core`. Keep the file so the import path
  `from rigour.names import Symbol` continues to resolve without
  touching downstream.
- `rigour/names/__init__.py` — nothing to change if `symbol.py`
  keeps the `Symbol` name.

Deleted:
- Nothing in this plan. `rigour/names/symbol.py` stays as the
  public import path, just re-exports.
