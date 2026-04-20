---
description: Design record for the Rust Symbol port — Arc<str> ids with a global interner, replacing Python's heterogeneous int-or-str id model
date: 2026-04-19
tags: [rigour, rust, symbols, names, memory]
status: implemented
---

# Rust Symbol: `Arc<str>` ids with a global interner

**Status: landed.** Implementation lives in `rust/src/names/symbol.rs`
(the header there links back to this doc). This record keeps the
design trade-offs so the "why not u32?" question doesn't have to be
re-litigated.

## Shape

```rust
pub struct Symbol {
    category: SymbolCategory,   // sealed enum, repr(u8), +7 B pad
    id: Arc<str>,               // 16 B (ptr + len); refcount in heap header
}
```

- `id` is always `Arc<str>`. Integer-source ids (Wikidata QIDs,
  ordinal numbers) are stringified at construction.
- All distinct id strings funnel through a global `intern()` function
  backed by `LazyLock<RwLock<HashMap<Box<str>, Arc<str>>>>`. One heap
  allocation per distinct string, shared via `Arc` refcount.
- `SymbolCategory` is a sealed `#[pyclass]` enum; variants are fixed
  data model (adding one is a cross-stack change).
- Breaking vs pre-port: `Symbol.id` is always `str` in Python now
  (was `int | str`).

## Why not `u32` + per-category string tables

Considered. Would get to 8 B per Symbol and ~24 MB at 3M Symbols (vs.
~76 MB with interned Arc). Abandoned because:

1. **Heterogeneous id model in `NAME`**. Wikidata QIDs, XIDs, and
   manual overrides legitimately share the `NAME` category but have
   different id conventions. Category-splitting breaks the conceptual
   bucket; bit-space partitioning is ugly and caps QIDs at 2³¹.
2. **Simplicity cost**. Tables, reverse lookups, and category-aware
   dispatch in the `Symbol.id` getter outweigh the ~50 MB saving.
3. **Arc<str> is idiomatic Rust**. Any maintainer reads it instantly;
   the u32-table scheme needs explanation every time it's touched.

## Memory footprint

Realistic tagger scale (3M Symbol instances; 158k unique ids):

| | Count | Per-item | Total |
|---|---|---|---|
| Symbol structs | 3M | 24 B | 72 MB |
| Interner entries | 158k | ~24 B | 3.8 MB |
| Interner HashMap overhead | 158k | ~40 B | 6 MB |
| **Total** | | | **~82 MB** |

Worst-case (10M Symbols): **~250 MB**. Compared with Python today
(~500–800 MB for 3M Symbols): meaningful win even before considering
the per-Symbol `__slots__` overhead.

## Follow-ups (not scheduled)

- **`compact_str`-style inline small strings.** Most of our ids fit
  in ≤ 24 B. Saves the interner entirely but loses sharing for
  repeated long-ish ids. Memory-wise within ~10% of interned Arc;
  simplicity-wise cleaner. Worth a spike later.
- **Category-local interners.** One per category rather than global.
  Enables `Symbol::eq` as pure `Arc::ptr_eq` without content fallback.
  Defer until profiling shows the single global `RwLock` is a
  bottleneck.
- **Per-process `Symbol` registry.** Assign each distinct
  `(category, id)` pair a dense `u32` at first construction; `Symbol`
  becomes a single `u32`. Big memory win at matching-index scale,
  more machinery. Possible end state.
- **Splitting `NAME` into semantic sub-categories.** Considered and
  rejected: the heterogeneous id model reflects real source diversity
  and the single bucket is the right place to absorb it. Revisit only
  if downstream matching ever needs distinct weights per source.
