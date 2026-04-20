---
description: Umbrella port plan for rigour's Rust core — phonetics, transliteration, normalisation, org-types, and the name tagger. Phases 1–4 landed; Phase 2 object-graph port and Phase 5 analyze_names pipeline remain.
date: 2026-04-19
tags: [rigour, nomenklatura, rust, performance, names, tagging, org-types, icu4x, maturin, pyo3]
status: Phases 1–4 landed; Phase 2 object-graph + Phase 5 pipeline pending
---

# Rust Port: rigour-core

## Context & Motivation

`entity_names` in `nomenklatura/matching/logic_v2/names/analysis.py`
is the hottest function in the matching stack. For every entity
comparison it runs prenormalize + tokenize, org-type replacement,
Aho-Corasick symbol tagging, and Name/NamePart object construction
with lazy-evaluated properties. Cold calls dominate at data load or
after cache eviction.

A previous attempt (Jan 2026, `fafo-rust` branch) used PyO3 directly
with `rust_icu_utrans` (ICU4C FFI via bindgen) and **was slower than
Python+PyICU** because the Rust/Python boundary was too fine-grained.
Lesson: **port larger chunks** so the hot loop runs entirely in Rust,
crossing the boundary only at coarse entry/exit points.

### Goals

1. Move the entire name analysis pipeline into Rust so it runs
   without crossing back to Python.
2. Drop `pyicu` by using ICU4X (pure Rust) for transliteration.
3. Fold in functionality from `normality`, `ahocorasick-rs`, and
   `jellyfish` so downstream Python deps shrink.
4. Reduce memory: Python `Name` / `NamePart` objects cost ~1–5 KB
   each; Rust structs cost ~200–400 bytes. At 200k names that's
   200–1000 MB vs 40–80 MB.

### Non-goals

- Pure-Python fallback.
- Porting nomenklatura's matching/scoring pipeline.
- Major version bump (will be 2.0 eventually, only when explicitly decided).

### Windows support

ICU4C → ICU4X pivot made every dependency pure Rust or first-class
Windows. One-row CI matrix addition; no source is Windows-aware. We
ship `win_amd64` wheels for Python 3.10–3.13. `win_arm64` skipped
until there's demand.

---

## Architectural Premises

**Only rigour contains Rust.** FTM, nomenklatura, and the rest of the
stack stay pure Python. They access Rust functionality through
rigour's normal Python API; the PyO3 bindings are an internal
implementation detail.

**All existing Python functions keep working.** `from rigour.names
import Name, tokenize_name, tag_person_name` etc. continue with the
same signatures. Upstream code gets updated to call coarser
Rust-backed entry points for performance, but the fine-grained API
remains.

**Eagerly compute derived properties.** PyO3 `#[pyclass]` objects
compute and cache `ascii`, `metaphone`, `comparable`, `integer`,
`latinize`, `numeric` at construction time in Rust. Avoids
per-attribute FFI overhead. `NamePart.tag` is the exception —
mutable via `#[pyo3(get, set)]` because the tagger modifies tags
after construction; safe because no other derived property depends
on `tag`.

**Symbol.id is always `str`.** Heterogeneous int-or-str IDs
stringified at data load. Simplifies Rust representation and the
PyO3 boundary.

---

## Build System

Maturin replaces hatchling. The Rust crate lives under `rust/`,
compiles to `rigour/_core.so`. A `python` Cargo feature gates the
PyO3 bindings so `cargo test` / `cargo build` work without a Python
runtime. The `rigour/py.typed` marker is required for downstream
`mypy --strict` to pick up the `.pyi` stubs.

CI wheel matrix (`PyO3/maturin-action@v1`): manylinux + musllinux
(x86_64, aarch64) × Python 3.10–3.13, macOS (x86_64, arm64),
Windows (x64). Publish-on-tag via `pypa/gh-action-pypi-publish`.
`make rust-data` regenerates everything under `rust/data/` +
`rust/src/generated/`; CI runs it and git-diffs against committed
artifacts.

See `pyproject.toml`, `rust/Cargo.toml`, and
`.github/workflows/build.yml` for the live config.

---

## ICU4X for Transliteration

Full design, benchmarks, and alternatives: `plans/rust-transliteration.md`.

- `icu` crate v2 with `compiled_data` + `unstable` features. No
  system ICU; ~3.4 MB of CLDR baked in.
- Pipeline: script detection → per-script transliterator → NFKD +
  nonspacing-mark removal → curated ASCII fallback. ICU4X lacks
  `Any-Latin`; we dispatch per-script.
- 22 script locales supported. Thai, Khmer, Lao, Sinhala, Tibetan
  pass through unchanged (not in `compiled_data` as of 2.2).
- `Transliterator` is `!Send + !Sync`: use `thread_local!` with a
  `RefCell` (not `LazyLock`). Python's GIL makes this effectively a
  process-lifetime cache.
- FFI is ~150 ns, not the bottleneck. Library is 1.3–5× slower than
  PyICU on most scripts; 11× slower on Chinese, 20× slower on
  three-script mixed inputs. Latin-diacritics is 10× *faster* via
  the ASCII fast-path. LRU cache masks this in production.

---

## Data Embedding Strategy

All resource data compiled into the Rust binary. No runtime file I/O
for data loading. The YAML/text files in `resources/` remain the
canonical human-edited source of truth; `genscripts/` emits
per-consumer artifacts under `rust/data/` and `rust/src/generated/`.

### Format choice: three tiers

**Tier 1 — Compressed pattern list, rebuild on first use.** Used for
the person-names corpus (~150k Aho-Corasick patterns). Plain UTF-8
committed at `rust/data/names/person_names.txt` for diffability;
`rust/build.rs` zstd-compresses (level 19, ~2.7 MB) into `OUT_DIR`;
`names::person_names` decodes via `include_bytes!` on first access.
Tagger builds the automaton inside a `LazyLock<AhoCorasick>` on
first access. 50–200 ms one-time cost per process.

*Why not precompiled AC bytes:* `aho-corasick` v1 exposes no serde
or raw-byte serialisation; implementing it ourselves would be
fragile and tied to the crate's private representation. If startup
cost ever becomes intolerable, evaluate `daachorse` (double-array AC
with explicit serialisation goals).

**Tier 2 — Sorted-slice `.rs` literals.** Used for the Unicode
script ranges, Latin/Latinizable sets, and similar small static
lookups. `genscripts/` emits `&'static [(K, V)]` / `&'static [(u32,
u32, Script)]` slice literals into `rust/src/generated/`. Lookup is
`slice::binary_search_by_key` — competitive with `phf` at our sizes
and vastly simpler to generate.

**Tier 3 — JSON(L) inside `LazyLock`.** Used for org types,
territories, org/person symbol dictionaries. A few hundred to few
thousand structured records with nested optional fields. Parse cost
is sub-millisecond; JSON is human-inspectable if a regeneration
looks wrong.

### Formats explicitly rejected

- **bincode / postcard / rkyv across the board**: diff-hostile,
  zero-copy gains are irrelevant post-init.
- **MessagePack**: same tradeoff, no benefit at these sizes.
- **YAML at runtime (`serde_yaml`)**: unnecessary dep, slower than
  JSON.
- **Embedding Python source**: closed-off non-starter.

### Source-of-truth vs. generated artifact

Migration is driven by the Rust pipeline's needs, not by a goal of
unifying the data layer. Datasets that only Python ever reads stay
Python-consumed. The current retirement state of `rigour/data/` is
tracked in `plans/rust-data-retirement.md`.

### Genscripts stays Python

The generators use the Python ecosystem (Wikidata client,
unidecode, existing rigour utilities), run rarely, and rewriting
them would be disproportionate effort. The clean split: **Python
generates, Rust consumes.** `make rust-data` + CI no-diff check is
the contract.

### Lazy initialisation

`std::sync::LazyLock<T>` is the direct analogue of Python no-arg
`@cache`. First-access init, thread-safe, held for process life, no
synchronisation cost on reads. Exception: `!Send`/`!Sync` types (ICU4X
`Transliterator`) use `thread_local!` with `RefCell`. Under GIL this
is effectively a process-lifetime singleton.

LRU caches are **always Python-side**, never in Rust — the principle
is "cache at the boundary to skip FFI." See *Key Design Decisions*
below for the case-by-case rule.

---

## What's landed

Phases 0, 0.5, 1, 3, 4 are complete. Short pointers:

- **Phase 0 — test corpus + ICU4X / maturin spikes.** Tests in
  `tests/text/test_transliteration.py`, `tests/names/test_tokenize.py`,
  `tests/text/test_scripts.py` expanded to pin behaviour pre-port.
- **Phase 0.5 — phonetics MVP.** `metaphone` / `soundex` via the
  `rphonetic` crate (jellyfish's Rust crate couldn't be used as a
  library dep; it's cdylib-only and conflicts with our pyo3).
- **Phase 1 — text primitives.** `ascii_text`, `latinize_text`,
  `codepoint_script`, `text_scripts`, `tokenize_name`,
  `prenormalize_name`, `normalize_name` all Rust-backed. Unicode
  script ranges + Latin sets as Tier-2 slice literals.
- **Phase 3 — org-type replacement + prefix removal.**
  `replace_org_types_compare` / `_display`, `remove_org_types`,
  `extract_org_types` via the `Needles<T>` substrate in
  `rust/src/names/matcher.rs` — aho-corasick with Python-style
  `(?<!\w)X(?!\w)` post-filter boundaries. Prefix removal stays in
  `rigour/names/prefix.py` with zero-arg `@cache`'d regex getters
  reading the Rust-owned prefix lists.
- **Phase 4 — AC tagger.** `tag_org_matches` / `tag_person_matches`
  with a `(TaggerKind, Normalize)`-keyed cache. Design record:
  `plans/rust-tagger.md`. Data resources (stopwords, ordinals,
  symbols, territories, person_names) are all Rust-owned under
  `rust/data/`. Python `rigour/names/tagging.py` is a thin wrapper.
  `ahocorasick-rs` dropped from `pyproject.toml`.
- **Symbol port** (Phase 2 prep). `Arc<str>` interner + sealed
  `SymbolCategory` enum. Design record: `plans/rust-symbols.md`.
- **Normalizer design** (`Normalize` bitflags + `Cleanup` enum).
  Design record: `plans/rust-normalizer.md`.
- **`string_number` port.** Collapsed to `rigour._core.string_number`
  via `rust/src/text/numbers.rs` — the `rigour/text/numbers.py`
  wrapper was retired after the port since the only consumers are
  `rigour/names/part.py` and `tests/text/test_numbers.py`. Fast
  path for ASCII via `f64::from_str`, hand-coded tables for Unicode
  decimal digit blocks (Arabic-Indic, Devanagari, fullwidth, etc.),
  Roman numerals in U+2160..U+2188, vulgar fractions, and CJK
  numerals. Fixes two latent Python bugs: `"3½"` was 30.5 (now
  None), `"ⅯⅮⅭ"` was 105100 (now None). Also filters inf/NaN
  outputs via an `is_finite()` guard — 400-digit strings no longer
  leak infinity.
- **Phase 6 — `pick_name` port.** `rigour.names.pick.pick_name` →
  `rigour._core.pick_name` via `rust/src/names/pick.rs`. **4.5×
  speedup** on the `benchmarks/bench_pick_name.py` harness (100k
  synthetic picks with 1–20 multi-script candidates). Design
  record: `plans/rust-pick-name.md`. Key subtleties that turned out
  to matter for parity: Python's `defaultdict(float)` aggregation
  ties scores by float-accumulation order, so the Rust port
  reproduces Python's `combinations(entries, 2)` add sequence on
  an O(M²) unique-string similarity matrix rather than a
  count-based shortcut. Also added a thread-local LRU-ish cache to
  Rust `ascii_text` — without it, pick_name was actually *slower*
  than Python because Python's `@lru_cache` on the Python wrapper
  was absorbing the cost.

Downstream adapter migration (nomenklatura / yente / FTM switching
from `normalizer=` callback to `normalize_flags=`) is tracked as the
last step of `plans/rust-tagger.md` and is owned by those repos.

---

## Remaining work

### Phase 2: `Name` / `NamePart` / `Span` object-graph port

**Goal**: move the core data model to Rust `#[pyclass]` types so
construction, derived-property computation, and mutation happen in
Rust. This is what unlocks the `analyze_names` single-FFI pipeline
in Phase 5.

**Rust structs** (sketch — `form` / `ascii` / `comparable` /
`metaphone` fields store `Py<PyString>`, not `String`, so repeated
attribute reads from Python are an INCREF, not a fresh alloc):

```rust
#[pyclass]
pub struct NamePart {
    pub form: Py<PyString>,
    pub index: Option<u32>,
    #[pyo3(get, set)]
    pub tag: NamePartTag,          // mutable — tagging pipeline writes this
    pub latinize: bool,            // eager: can_latinize(form)
    pub numeric: bool,             // eager: all chars numeric
    pub ascii: Option<Py<PyString>>,
    pub integer: Option<i64>,
    pub comparable: Py<PyString>,
    pub metaphone: Option<Py<PyString>>,
    hash: u64,                     // precomputed
}

#[pyclass]
pub struct Span {
    #[pyo3(get)] pub parts: Vec<NamePart>,  // owned clones, not indices
    #[pyo3(get)] pub symbol: Symbol,
    #[pyo3(get)] pub comparable: Py<PyString>,
}

#[pyclass]
pub struct Name {
    pub original: Py<PyString>,
    pub form: Py<PyString>,
    #[pyo3(get, set)] pub tag: NameTypeTag,
    pub lang: Option<Py<PyString>>,
    #[pyo3(get)] pub parts: Vec<NamePart>,
    #[pyo3(get)] pub spans: Vec<Span>,
}
```

`Span` owns cloned parts rather than indices — once a `Span` reaches
Python it has no back-reference to its parent `Name` to resolve
indices. `NamePart` is `Clone` and small (~200 B heap), so copying
matches the current Python semantics where `Span.parts = tuple(parts)`.

`#[pyo3(get)]` on a `String` field allocates a fresh `PyString` on
every attribute read (UTF-8 validation + heap alloc, ~150–300 ns).
`Py<PyString>` caches the interned Python object at construction;
subsequent reads are an INCREF (~60–100 ns), comparable to a native
`__slots__` attribute.

### Phase 5: `analyze_names` single-FFI pipeline

Design lives in `plans/rust-names-parser.md`. Shape:

```python
# rigour/names/analysis.py
def analyze_names(
    names: list[str],
    type_tag: NameTypeTag,
    part_tags: Mapping[NamePartTag, Sequence[str]],
    *,
    infer_initials: bool = False,
) -> set[Name]: ...
```

One call does tokenization + prenormalize + prefix removal +
org-type replacement + AC tagging + `Name` / `NamePart` / `Span`
construction. The FTM-side `entity_names` adapter collapses to a
thin wrapper. Prerequisites: Phase 2 object-graph port for the
returned `Name` instances.

### Phase 6 follow-ups in `rigour.names.pick`

**`pick_name` itself is ported** (see the landed list above —
4.5× speedup on the 100k-pick benchmark). The sibling helpers in
`rigour/names/pick.py` stay Python: `pick_lang_name` is a thin
language-filter wrapper, `pick_case` is case-bias scoring on
identical-content inputs, `reduce_names` dedupes a name list.
Port only if profiling shows any of them hot; `pick_name` was the
O(n²) centroid that justified the move.

---

## Normality Subsumption

Dependency stack: **normality → rigour → followthemoney →
nomenklatura**.

With Phase 1 landed, rigour can begin dropping normality:

1. rigour implements all needed normality functionality in
   `rigour.text.*` (ascii_text/latinize_text Rust-side; squash_spaces
   / category_replace / WS / Categories / UNICODE_CATEGORIES as pure
   Python).
2. Replace `from normality import X` with `from rigour.text import X`.
3. Drop `normality` from `pyproject.toml`.
4. followthemoney switches its normality imports to `rigour.text`.
5. nomenklatura does the same.
6. normality becomes unreferenced in the stack.

Steps 1–3 are local to rigour and ready to land. Steps 4–5 are owned
by those repos' respective PRs.

---

## Rust Crate Dependencies

Live config is `rust/Cargo.toml`. Current set (as of April 2026):

- `pyo3` 0.28 — `extension-module` + `generate-import-lib`
  (Windows-friendly link stub).
- `icu` 2 — `compiled_data` + `unstable` for transliteration.
- `bitflags` 2 — `Normalize` flag set.
- `rphonetic` 3 — metaphone, soundex.
- `rapidfuzz` 0.5 — string distance for the Rust-internal name
  picker (not exposed via PyO3; see *Known gap* below).
- `aho-corasick` 1 — multi-needle literal search for `Needles<T>`
  (backs org_types + tagger).
- `serde` / `serde_json` — Tier-3 JSON loaders.
- `zstd` 0.13 — person-names corpus compression at build time.

MSRV: 1.86 (pinned by `icu` 2.2).

### Known gap: Rust `rapidfuzz` has no `opcodes` API

Python `rapidfuzz` exposes `Levenshtein.opcodes(s1, s2)` for
alignment recovery; nomenklatura's `_opcodes` is `@lru_cache`'d over
it. The Rust `rapidfuzz` 0.5 crate has no equivalent — distance /
similarity scores only.

Implication: a Rust-side distance port would leave the Python
rapidfuzz dep in place anyway for opcodes, providing no dep
reduction. Python rapidfuzz's C++ backend already runs the same
bit-parallel algorithms, so there's no speed regression from
keeping distance on the Python side.

Plan of record: **keep Python rapidfuzz until Phase 5 forces the
question.** Three options at that point:

- **(A)** Keep Python rapidfuzz for distance + opcodes. No rigour
  Rust bindings for distance. Simplest.
- **(B)** Rust-side distance + Python-side opcodes. Mostly pointless
  (no net dep reduction).
- **(C)** Implement opcodes in Rust (port Hyyrö's bit-parallel
  alignment from `rapidfuzz-cpp`, or Wagner-Fischer with traceback).
  Real implementation effort. Or upstream the opcodes API to the
  Rust rapidfuzz crate.

Do not half-port distance without re-reading this block.

---

## Key Design Decisions & Rationale

The "don't re-litigate this" list.

### LRU caches: case-by-case, not blanket removal

- **Transliteration, tokenisation**: Rust is microseconds; diverse
  inputs; cache lookup dominates. **Drop the LRU.**
- **Phonetics (metaphone, soundex)**: Rust is ~1 µs, FFI crossing
  ~500 ns. Matching pounds on the same tokens ("John", "Smith",
  "Sergei") at 90%+ hit rates. Cache avoids FFI on hits. **Keep
  `@lru_cache(maxsize=MEMO_LARGE)`.**
- **Distance**: original caches were tiny (2k). Workload-dependent;
  re-evaluate in Phase 5 if distance lands Rust-side.

An earlier revision said "LRU caches go away" categorically; the
Phase 0.5 MVP proved that too strong. Keep when the underlying call
isn't dramatically faster than the cache lookup itself.

LRU caches never live in Rust — always Python-side fast-paths that
skip the FFI.

### Why eager derived properties

Per-attribute FFI calls are death by a thousand cuts. Computing
`ascii`, `comparable`, `metaphone`, `integer`, `latinize`, `numeric`
at construction pays once; attribute reads become field reads
(~50 ns, same as any C extension).

### Why `NamePart.tag` is mutable but others aren't

`tag_text` / `_infer_part_tags` write `part.tag` after construction.
None of the eagerly-computed properties depend on `tag` — they
depend on `form` — so mutation doesn't invalidate cached values.

### Why `Span` owns cloned parts (not indices)

Once a `Span` is handed to Python, it has no back-reference to its
parent `Name` to resolve indices. `NamePart` is `Clone` and small
(~200 B heap); owning copies matches current Python semantics
(`self.parts = tuple(parts)`) and keeps `Span` self-contained.
Within pure-Rust code an index representation is fine, converting at
the PyO3 boundary.

### Why `Symbol.id` is always `String`

Heterogeneous `int | str` IDs (Python legacy — GeoNames numerics as
`int`, everything else as `str`) complicates the Rust type and the
PyO3 boundary. Numeric IDs stringified at data load. See
`plans/rust-symbols.md`.

### Why embed data in the binary

No file-path resolution, no `importlib.resources`, no `__file__`
hacks. The Rust binary is self-contained. Person-names corpus
compresses 8.5 MB → ~2.7 MB; total wheel size impact is acceptable
for a server-side library.

### Why `\b` word boundaries over lookaround

The `regex` crate doesn't support lookahead/lookbehind. For the
literal-alias matching we do, Python-style `(?<!\w)X(?!\w)` is
implemented as a post-filter on aho-corasick matches — see
`rust/src/names/matcher.rs`. CJK limitation (CJK chars are `\w`, so
`\b` doesn't fire between them) matches the existing Python
behaviour exactly.

---

## Dependency Removal Roadmap

| Phase | Dropped Python dep | Replaced by |
|-------|--------------------|-------------|
| 1 | `pyicu` | `icu` crate (ICU4X) |
| 1+ | `normality` | `rigour.text.*` (Rust + pure Python) |
| 0.5 | `jellyfish` | `rphonetic` crate (metaphone, soundex) |
| 4 | `ahocorasick-rs` | `aho-corasick` crate |
| — | `rapidfuzz` | **Not removed.** Opcodes gap. See Phase 2 known-gap block. |
| — | `fingerprints` | Review after org_types land. |

---

## Open Questions

1. **Rust-side distance: gated by opcodes gap.** See *Rust Crate
   Dependencies → Known gap*. Revisit in Phase 5.

2. **`rapidfuzz` Rust crate maintenance**: v0.5.0 (December 2023).
   Moot until we depend on it. If we do, API surface is tiny;
   fallback is pin a SHA or port ~300 lines ourselves.

3. **`rphonetic` maintenance**: actively maintained; unlike
   `jellyfish` (v1.0, June 2023, static). Metaphone/soundex don't
   evolve — tolerable risk either way.

4. **`lru_cache` on `entity_names`**: once `analyze_names` runs in
   Rust (Phase 5), the cache may be unnecessary. Remove and benchmark.

5. **Person tagger startup cost**: 50–200 ms for zstd decode + AC
   construction on first tagger access (estimated). Measure in a
   production context; if intolerable, evaluate `daachorse`.

6. **Free-threaded Python (PEP 703 / `python3.13t`)**: the
   `thread_local!` pattern for ICU4X relies on the GIL. Under
   free-threaded builds, each OS thread pays transliterator init
   separately (~900 µs). Decision needed: `abi3` wheels only, or add
   `cp313t`/`cp314t` to the matrix.

7. **`analyze_names` API shape (Phase 5)**: kwargs function vs.
   `#[pyclass] AnalyzeRequest`. Leaning toward the pyclass
   (type-safe, extensible). Decided at Phase 5 implementation time.

### Resolved (for the record)

- **Build backend**: hatchling → maturin, plain replacement.
- **Wheel size**: net-neutral to net-smaller than pre-port.
- **`consolidate_names` return type**: `Vec<Name>` (semantics
  collapse-shorter-into-longer by `contains()`, not strict equality).
- **ICU4X binary size**: 3.4 MB for all transliteration data.
- **`genscripts/` format**: three-tier strategy above. Python
  generates, Rust consumes.
- **Rust crate versions / MSRV**: pinned in `rust/Cargo.toml`. MSRV
  1.86.
- **Phonetics crate**: `rphonetic` (not `jellyfish` as crate dep;
  `jellyfish` is cdylib-only and conflicts with our pyo3).
- **jellyfish for phonetics, Rust-side distance deferred**: opcodes
  gap above. Phase 0.5 landed phonetics via `rphonetic`; distance
  stays Python for now.
