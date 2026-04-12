---
description: Port rigour's name analysis pipeline and text primitives to Rust via rigour-core with ICU4X, PyO3, and maturin
date: 2026-04-12
tags: [rigour, nomenklatura, rust, performance, names, tagging, org-types, icu4x, maturin, pyo3]
---

# Rust Port: rigour-core

## Context & Motivation

`entity_names` in `nomenklatura/matching/logic_v2/names/analysis.py` is the hottest function
in the matching stack. For every entity comparison it runs: prenormalize + tokenize (per name),
org type replacement (regex Replacer), Aho-Corasick symbol tagging, and Name/NamePart object
construction with lazy-evaluated properties (ascii, metaphone, comparable). Cold calls dominate
at data load time or after cache eviction.

A previous attempt (Jan 2026, `fafo-rust` branch) used PyO3 directly with `rust_icu_utrans`
(ICU4C FFI via bindgen). **It was slower than the Python+PyICU implementation** because the
Rust/Python boundary was too fine-grained — individual function calls like `ascii_text(str)`
didn't amortize the FFI overhead. The key lesson: **port larger chunks** so that the hot loop
runs entirely in Rust, crossing the boundary only at coarse entry/exit points.

### Goals

1. Move the entire name analysis pipeline into Rust so it runs without crossing back to Python
2. Drop the `pyicu` dependency by using ICU4X (pure Rust) for transliteration
3. Fold in functionality currently spread across `normality`, `ahocorasick-rs`, `jellyfish`,
   and `rapidfuzz` into one Rust crate — reducing the Python dependency count while reusing
   the same underlying Rust crates (`jellyfish`, `rapidfuzz`, `aho-corasick`)
4. Reduce memory footprint: Python `Name`/`NamePart` objects cost ~1-5KB each; Rust structs
   cost ~200-400 bytes. For a nomenklatura index with 200k names, this is 200-1000MB vs 40-80MB

### Non-Goals

- Windows support
- Pure-Python fallback (all developers and CI must have a Rust toolchain)
- Porting the matching/scoring pipeline from nomenklatura (separate future work)
- Major version bump (will be 2.0 eventually, but only when explicitly decided)

---

## Architectural Premises

**Only rigour contains Rust.** FTM, nomenklatura, and all other libraries in the stack remain
pure Python. They access Rust functionality exclusively through rigour's normal Python API. The
PyO3 bindings are an internal implementation detail of rigour, invisible to callers.

**All existing Python functions keep working.** `from rigour.names import Name, tokenize_name,
tag_person_name` etc. continue to work with the same signatures. Upstream code (nomenklatura)
will be updated to call coarser Rust-backed functions for performance, but the fine-grained
API remains available.

**Eagerly compute all derived properties.** PyO3 `#[pyclass]` objects compute and cache all
derived fields (ascii, metaphone, comparable, integer, latinize, numeric) at construction time
in Rust. This avoids per-attribute FFI overhead when Python code reads properties. The cost is
paid once, in Rust, during the hot loop. Note: `NamePart.tag` is the exception — it is mutable
(`#[pyo3(get, set)]`) because the tagging pipeline modifies tags after initial construction.
This is safe because no other derived property depends on `tag`.

**Symbol.id is always `str`.** GeoNames numeric IDs are converted to strings at data load time.
This simplifies the Rust representation (`String` not an enum) and the PyO3 boundary.

---

## Build System

### Maturin as Build Backend

Replace hatchling with maturin in `pyproject.toml`. Maturin handles:
- Compiling the Rust crate via cargo
- Producing Python wheels with the compiled `.so`/`.dylib`
- Supporting mixed Python+Rust projects (Python in `rigour/`, Rust in `rust/`)

```toml
[build-system]
requires = ["maturin>=1.7,<2.0"]
build-backend = "maturin"

[tool.maturin]
features = ["pyo3/extension-module"]
module-name = "rigour._core"
manifest-path = "rust/Cargo.toml"
```

The Rust crate compiles to `rigour/_core.so` — a private module. Python code imports from it:

```python
# rigour/text/transliteration.py
from rigour._core import ascii_text as _ascii_text

def ascii_text(text: str) -> str:
    if text.isascii():
        return text
    return _ascii_text(text)
```

### Repository Layout

```
rigour/
├── rust/                          # Rust crate
│   ├── Cargo.toml
│   ├── Cargo.lock
│   ├── src/
│   │   ├── lib.rs                 # PyO3 module definition
│   │   ├── text/
│   │   │   ├── mod.rs
│   │   │   ├── transliterate.rs   # ICU4X ascii_text, latinize_text
│   │   │   ├── scripts.rs         # can_latinize, is_latin, is_dense_script
│   │   │   └── tokenize.rs        # tokenize_name, prenormalize, normalize
│   │   ├── names/
│   │   │   ├── mod.rs
│   │   │   ├── part.rs            # NamePart with eager properties
│   │   │   ├── name.rs            # Name with tag_text, apply_phrase, contains
│   │   │   ├── symbol.rs          # Symbol (category: enum, id: String)
│   │   │   ├── span.rs            # Span (owns cloned parts)
│   │   │   ├── tag.rs             # NameTypeTag, NamePartTag enums
│   │   │   ├── tagger.rs          # Aho-Corasick tagger + word boundary matching
│   │   │   ├── org_types.rs       # Replacer for org type normalization
│   │   │   ├── prefix.rs          # remove_person_prefixes, remove_org_prefixes
│   │   │   └── analysis.rs        # analyze_names (the big pipeline function)
│   │   ├── phonetics.rs           # jellyfish crate: metaphone, soundex
│   │   └── distance.rs            # rapidfuzz crate: levenshtein, jaro_winkler
│   ├── data/                      # Embedded resource files (generated by genscripts/)
│   │   ├── scripts.json
│   │   ├── stopwords.json
│   │   └── ...
│   └── benches/
│       └── names.rs               # Criterion benchmarks
├── rigour/                        # Python package (unchanged structure)
│   ├── _core.pyi                  # Type stubs for the Rust extension (REQUIRED for mypy)
│   ├── text/
│   │   ├── transliteration.py     # NEW: exposes ascii_text, latinize_text with fast-paths
│   │   ├── scripts.py             # Updated: delegates to _core
│   │   └── ...
│   ├── names/
│   │   ├── tokenize.py            # Updated: delegates to _core
│   │   ├── part.py                # Updated: re-exports _core.NamePart, _core.Span
│   │   ├── name.py                # Updated: re-exports _core.Name
│   │   ├── analysis.py            # NEW: analyze_names wrapper
│   │   └── ...
│   └── ...
├── resources/                     # Source YAML/text files (unchanged)
├── genscripts/                    # Generation scripts (extended to emit JSON for Rust)
├── tests/                         # Python tests (unchanged, expanded)
└── pyproject.toml                 # Maturin build backend
```

### CI/CD Targets

GitHub Actions matrix using `maturin-action`:

| OS | Architecture | Python | Wheel tag |
|----|-------------|--------|-----------|
| Ubuntu (manylinux) | x86_64 | 3.10-3.13 | manylinux_2_17_x86_64 |
| Ubuntu (manylinux) | aarch64 | 3.10-3.13 | manylinux_2_17_aarch64 |
| Ubuntu (musllinux) | x86_64 | 3.10-3.13 | musllinux_1_2_x86_64 |
| Ubuntu (musllinux) | aarch64 | 3.10-3.13 | musllinux_1_2_aarch64 |
| macOS | x86_64 | 3.10-3.13 | macosx_10_12_x86_64 |
| macOS | arm64 | 3.10-3.13 | macosx_11_0_arm64 |

Source distribution (`sdist`) also published for `pip install` from source (requires Rust
toolchain + maturin).

---

## ICU4X for Transliteration

### Why ICU4X Instead of ICU4C

The previous attempt used `rust_icu_utrans` which wraps ICU4C via bindgen. Problems:
- Requires ICU4C headers and libraries at build time
- Creates linking headaches for manylinux wheel distribution (must bundle or static-link ICU)
- The Python→Rust→ICU4C double-hop didn't outperform Python→ICU4C (PyICU) directly

**ICU4X** (`icu` crate) is the ICU team's pure-Rust rewrite. Advantages:
- Compiles statically, no system dependency
- Data baked into the binary (CLDR data via `compiled_data` feature)
- Designed for exactly this use case (embedding in libraries)

### Transliteration in ICU4X

ICU4X has experimental transliteration support via the `icu::transliterator` module.
The API accepts ICU transliterator rule strings. The exact API needs verification during
implementation — the snippet below is illustrative:

```rust
use icu::transliterator::Transliterator;
use std::sync::LazyLock;

// Equivalent to normality's ASCII_SCRIPT:
// "Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Latin-ASCII"
static ASCII_TRANS: LazyLock<Transliterator> = LazyLock::new(|| {
    // API may be try_new_with_compiled_data() or similar — verify against
    // the actual icu crate v2 docs during implementation.
    Transliterator::try_new(
        "Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Latin-ASCII".parse().unwrap(),
    ).expect("ICU4X ASCII transliterator")
});

/// Transliterate to ASCII. The Python wrapper handles the is_ascii() fast-path;
/// this function only receives non-ASCII input.
pub fn ascii_text(s: &str) -> String {
    let mut result = ASCII_TRANS.transliterate(s.to_string());
    // Fallback for anything ICU4X couldn't handle:
    result.retain(|c| c.is_ascii());
    result
}
```

### Data Provider Strategy

ICU4X uses data providers for CLDR/Unicode data. With the `compiled_data` Cargo feature,
data for all supported operations is baked into the binary at compile time. This adds ~2-5MB
to the binary size, which is acceptable for a server-side library.

If binary size becomes a concern, `icu_datagen` can generate data for only the specific
transliteration rules we need — but start with `compiled_data` for simplicity.

### Validation

The ICU4X transliterator may produce slightly different output than PyICU/ICU4C for edge cases
(different CLDR versions, different rule implementations). Strategy:

1. Build a test corpus from all existing test vectors in `tests/text/` and `tests/names/`
2. Run both PyICU and ICU4X on the corpus, diff the results
3. Accept differences that are "equally correct" (e.g. different Pinyin romanizations)
4. File ICU4X bugs for differences that are clearly wrong
5. Add `tests/text/test_transliteration_corpus.py` that pins expected outputs

**Goal: drop `pyicu` from rigour's dependencies once ICU4X transliteration is validated.**

---

## Data Embedding Strategy

All resource data compiled into the Rust binary. No runtime file I/O for data loading.

### Sources and Embedding

`genscripts/` is extended to produce JSON files (in `rust/data/`) alongside the existing
Python data files. Both formats are generated from the same upstream YAML/text sources.

| Resource | Upstream source | Approx size | Embedding |
|----------|----------------|-------------|-----------|
| Unicode script ranges | Unicode data via genscripts | ~50KB JSON | `include_str!` + serde, parsed into lookup at startup |
| Latin/Latinizable chars | Unicode data via genscripts | ~30KB JSON | `include_str!` + parsed into `HashSet<u32>` |
| Stopwords, nullwords | `resources/` YAML via genscripts | ~5KB JSON | `include_str!` |
| Org types | `resources/names/org_types.yml` | ~60KB YAML | `include_str!` + serde_yaml at startup |
| Org symbols, domains | `resources/` YAML via genscripts | ~20KB JSON | `include_str!` |
| Person symbols, nicks | `resources/` YAML via genscripts | ~15KB JSON | `include_str!` |
| Person name corpus | `resources/names/names/*.gz` via genscripts | ~8.5MB text | `include_bytes!` zstd-compressed, lazy decompress |
| Ordinals | `resources/` YAML via genscripts | ~10KB JSON | `include_str!` |
| Territories | `resources/territories/` via genscripts | ~200KB JSONL | `include_str!` |

### Lazy Initialization

All data structures (taggers, org type replacers, script lookup tables) initialized on first
use via `std::sync::LazyLock`. This mirrors the Python `@cache` pattern and avoids paying
startup cost for codepaths that aren't used.

The person names corpus (~8.5MB) is zstd-compressed at generation time and embedded as
`include_bytes!`. On first tagger access, it's decompressed and parsed into the Aho-Corasick
automaton. This adds ~50-100ms one-time startup cost but keeps wheel size manageable.

---

## Phased Implementation

### Phase 0: Test Corpus + Feasibility Spikes

**Goal**: De-risk Phase 1 by expanding test coverage (so we can detect regressions when
swapping in Rust) and validating that ICU4X and maturin work for our use case.

**Test corpus expansion**:

- **Transliteration**: Add test vectors for all target languages — Arabic, Simplified Chinese,
  Japanese, Korean, Cyrillic (Russian, Ukrainian), Greek, Georgian, Armenian, Turkish, Polish,
  Hungarian, Portuguese, Swedish, Norwegian, Danish, Lithuanian, Estonian, Finnish, Dutch, German,
  French, Spanish. Pin expected `ascii_text` and `latinize_text` outputs. These become the
  regression suite for the ICU4X transition.
- **`tokenize_name`**: Add edge cases for exotic punctuation (e.g. middle dot `·`, Armenian
  comma, CJK fullwidth punctuation), combining marks, zero-width characters, rare Unicode
  categories. Pin expected token lists.
- **Script detection**: Add test cases for `can_latinize`, `is_latin`, `is_modern_alphabet`,
  `is_dense_script` covering boundary codepoints — last Latin codepoint, first Cyrillic, Hangul
  Jamo vs. syllables, CJK Unified Ideographs extensions, etc.

**ICU4X spike** (throwaway code):

- `cargo new icu4x-spike` in a temporary directory
- Add `icu = { version = "2", features = ["transliteration", "compiled_data"] }`
- Run our exact transliterator rule strings:
  - `"Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Latin-ASCII"` (ascii_text)
  - `"Any-Latin"` (latinize_text)
- Feed the test corpus through both rules, compare output against PyICU
- Measure: binary size impact of `compiled_data`, transliteration throughput (ops/sec),
  startup time for `LazyLock` initialization
- **Decision gate**: If ICU4X output is unacceptably different or the API can't handle our
  rules, revisit the transliteration strategy before proceeding to Phase 1

**Maturin spike** (throwaway code):

- Create a minimal `rust/Cargo.toml` + `rust/src/lib.rs` with a single PyO3 function
  (e.g. `fn hello() -> &str`)
- Switch `pyproject.toml` to maturin build backend
- Verify: `maturin develop` works, `pip install -e .` works, `import rigour._core` works,
  existing tests still pass, `mypy --strict` still passes with a `.pyi` stub
- Test the CI pipeline: maturin-action builds wheels for at least one platform
- **Decision gate**: If maturin integration has unexpected friction with the existing
  hatchling setup, resolve before Phase 1

**No code ships from Phase 0** — the test corpus is committed, the spikes are discarded
after they answer their questions.

---

### Phase 1: Build System + Text Primitives

**Goal**: Set up maturin, compile a Rust extension, expose the first functions. This phase
proves the build pipeline works end-to-end and delivers the ICU4X transliteration that
unblocks dropping `pyicu`.

**Rust functions** (in `rust/src/text/`):

| Function | Signature | Notes |
|----------|-----------|-------|
| `ascii_text` | `(s: &str) -> String` | ICU4X transliteration. Python fast-path handles `isascii()` |
| `latinize_text` | `(s: &str) -> String` | ICU4X `Any-Latin`. Python fast-path checks codepoints < 740 |
| `tokenize_name` | `(text: &str, min_length: usize) -> Vec<String>` | Iterator over chars, classify by Unicode category, split on whitespace |
| `prenormalize_name` | `(name: &str) -> String` | Unicode casefold |
| `normalize_name` | `(name: &str, sep: &str) -> Option<String>` | casefold + tokenize + join |
| `can_latinize` | `(word: &str) -> bool` | Check script membership |
| `is_latin` | `(word: &str) -> bool` | Check Latin codepoints |
| `is_modern_alphabet` | `(word: &str) -> bool` | Latin + Cyrillic + Greek + Armenian |
| `is_dense_script` | `(word: &str) -> bool` | Han, Hiragana, Katakana, Hangul |

**`tokenize_name` Rust idiom**: The current Python uses `str.translate()` with a lazy
`dict[int, Optional[int]]` lookup table. The idiomatic Rust equivalent is an iterator that
classifies each `char` via `unicode_general_category::get_general_category()` and maps it
to itself, a space, or nothing — then `split_whitespace()`. No HashMap, no caching, single
pass:

```rust
fn classify(c: char) -> Option<char> {
    if SKIP_CHARACTERS.contains(&c) { return None; }
    match get_general_category(c) {
        // Categories that become token separators (space):
        Cc | Zs | Zl | Zp | Pc | Pd | Ps | Pe | Pi | Pf | Po | Mc | Sm | So => Some(' '),
        // Categories that are deleted:
        Cf | Co | Cn | Lm | Mn | Me | No | Sc | Sk => None,
        // Everything else (letters, digits): keep as-is
        _ => Some(c),
    }
}

pub fn tokenize_name(text: &str, min_length: usize) -> Vec<String> {
    let mapped: String = text.chars().filter_map(classify).collect();
    mapped.split_whitespace()
        .filter(|t| t.len() >= min_length)
        .map(String::from)
        .collect()
}
```

**Python wrappers** — thin modules with fast-paths that avoid FFI for trivial cases:

```python
# rigour/text/transliteration.py
from rigour._core import _ascii_text, _latinize_text

LATIN_BLOCK = 740

def ascii_text(text: str) -> str:
    """Transliterate text to ASCII."""
    if text.isascii():
        return text
    return _ascii_text(text)

def latinize_text(text: str) -> str:
    """Transliterate text to Latin script."""
    if all(ord(c) < LATIN_BLOCK for c in text):
        return text
    return _latinize_text(text)
```

```python
# rigour/names/tokenize.py — delegates to _core, no LRU cache needed
from rigour._core import tokenize_name, prenormalize_name

def normalize_name(name: Optional[str], sep: str = " ") -> Optional[str]:
    if name is None:
        return None
    name = prenormalize_name(name)
    joined = sep.join(tokenize_name(name))
    return joined if len(joined) > 0 else None
```

```python
# rigour/text/scripts.py — delegates to _core
from rigour._core import can_latinize, is_latin, is_modern_alphabet, is_dense_script
```

**Data embedded**: Unicode script ranges, Latin/Latinizable character sets.

**New files**:
- `rust/Cargo.toml`, `rust/src/lib.rs`
- `rust/src/text/mod.rs`, `transliterate.rs`, `scripts.rs`, `tokenize.rs`
- `rigour/text/transliteration.py`
- `rigour/_core.pyi` — type stubs (**required**, without these mypy breaks for all downstream)
- `.github/workflows/build.yml` — updated CI with maturin-action

**Modified files**:
- `pyproject.toml` — maturin build backend, drop `pyicu` dependency
- `rigour/text/scripts.py` — delegate to `_core`
- `rigour/names/tokenize.py` — delegate to `_core`, remove LRU caches

**Dependency changes**: Drop `pyicu`. Begin inlining `normality` functions into
`rigour.text.*` (pure Python for `squash_spaces`, `category_replace`, `WS`, etc.).

**Validation**: All existing tests in `tests/text/` and `tests/names/test_tokenize.py` pass.
New test file `tests/text/test_transliteration.py` with comprehensive corpus.

---

### Phase 2: Data Structures + Phonetics + String Distance

**Goal**: Port the core data model to Rust `#[pyclass]` types. Phonetics and string distance
are included in this phase because `NamePart.metaphone` must work — shipping NamePart with
`metaphone = None` would break the matching pipeline downstream.

**Rust crate dependencies** for this phase:

```toml
jellyfish = "1"      # metaphone, soundex — same Rust crate used by the jellyfish Python package
rapidfuzz = "0.1"    # levenshtein, damerau-levenshtein, jaro-winkler — Rust crate from same author
```

Both `jellyfish` (Python package) and `rapidfuzz` (Python package) are backed by native code:
- **jellyfish**: Rust + PyO3. The `jellyfish` crate on crates.io is the same code.
  Using it as a Cargo dependency guarantees exact output parity.
- **rapidfuzz**: C++ Python package, but the same author maintains a `rapidfuzz` Rust crate
  on crates.io with the same algorithms. Need to verify output parity for edge cases.

**Rust structs**:

```rust
#[pyclass]
#[derive(Clone)]
pub struct Symbol {
    #[pyo3(get)]
    pub category: SymbolCategory,  // #[pyclass] enum
    #[pyo3(get)]
    pub id: String,                // always String (GeoNames numeric IDs converted at load time)
}

#[pyclass]
#[derive(Clone)]
pub struct NamePart {
    #[pyo3(get)]
    pub form: String,
    #[pyo3(get)]
    pub index: Option<u32>,
    #[pyo3(get, set)]
    pub tag: NamePartTag,          // MUTABLE — tagging pipeline modifies after construction
    #[pyo3(get)]
    pub latinize: bool,            // computed at construction: can_latinize(form)
    #[pyo3(get)]
    pub numeric: bool,             // computed at construction: form.chars().all(|c| c.is_numeric())
    #[pyo3(get)]
    pub ascii: Option<String>,     // computed at construction: ascii_text + retain(|c| c.is_alphanumeric())
    #[pyo3(get)]
    pub integer: Option<i64>,      // computed at construction: parse numeric forms
    #[pyo3(get)]
    pub comparable: String,        // computed at construction: ascii if latinizable, else form
    #[pyo3(get)]
    pub metaphone: Option<String>, // computed at construction: jellyfish::metaphone if latinize && !numeric && len > 2
    hash: u64,                     // precomputed: hash(index, form)
}
```

**Why `tag` is mutable but derived properties are not**: `tag_text()` and `_infer_part_tags()`
modify `part.tag` after the `Name` is constructed. But none of the eagerly-computed properties
(`ascii`, `comparable`, `metaphone`, `latinize`, `numeric`, `integer`) depend on `tag` — they
depend only on `form`. So mutating `tag` doesn't invalidate any cached value.

**`Span` owns cloned parts** (not indices):

```rust
#[pyclass]
#[derive(Clone)]
pub struct Span {
    #[pyo3(get)]
    pub parts: Vec<NamePart>,      // owned copies of the NamePart objects
    #[pyo3(get)]
    pub symbol: Symbol,
    #[pyo3(get)]
    pub comparable: String,        // precomputed: space-joined part.comparable values
}
```

The previous plan stored `Vec<usize>` indices into the parent `Name.parts`, but this doesn't
work: once a `Span` is handed to Python, it has no back-reference to its parent `Name` to
resolve the indices. Since `NamePart` is `Clone` and small (~200 bytes of heap data), owning
copies is cheap and matches the current Python semantics where `Span.parts` is `tuple(parts)`
referencing the same objects.

Within pure Rust code (the `analyze_names` pipeline), the internal representation could use
indices for efficiency, converting to owned copies only at the PyO3 boundary. But this is an
optimization to consider later, not a first-pass requirement.

**`Name`** is a `#[pyclass]` with methods:

```rust
#[pyclass]
pub struct Name {
    #[pyo3(get)]
    pub original: String,
    #[pyo3(get)]
    pub form: String,
    #[pyo3(get, set)]
    pub tag: NameTypeTag,          // mutable — _infer_part_tags can upgrade ENT to ORG
    #[pyo3(get)]
    pub lang: Option<String>,
    #[pyo3(get)]
    pub parts: Vec<NamePart>,
    #[pyo3(get)]
    pub spans: Vec<Span>,
}

#[pymethods]
impl Name {
    fn tag_text(&mut self, text: &str, tag: NamePartTag, max_matches: Option<usize>);
    fn apply_phrase(&mut self, phrase: &str, symbol: &Symbol);
    fn apply_part(&mut self, part: &NamePart, symbol: &Symbol);
    #[getter]
    fn comparable(&self) -> String;    // computed on access (cheap: join part.comparable)
    #[getter]
    fn norm_form(&self) -> String;     // computed on access (cheap: join part.form)
    #[getter]
    fn symbols(&self) -> HashSet<Symbol>;
    fn contains(&self, other: &Name) -> bool;
    #[staticmethod]
    fn consolidate_names(names: Vec<Name>) -> HashSet<Name>;
}
```

**String distance functions** exposed via PyO3:

```rust
// Wrappers around the rapidfuzz crate
#[pyfunction]
pub fn levenshtein(left: &str, right: &str, max_edits: Option<usize>) -> usize;
#[pyfunction]
pub fn dam_levenshtein(left: &str, right: &str, max_edits: Option<usize>) -> usize;
#[pyfunction]
pub fn jaro_winkler(left: &str, right: &str) -> f64;
#[pyfunction]
pub fn levenshtein_similarity(left: &str, right: &str, max_edits: usize, max_percent: f64) -> f64;
```

**Phonetics** exposed via PyO3:

```rust
// Wrappers around the jellyfish crate
#[pyfunction]
pub fn metaphone(token: &str) -> String;
#[pyfunction]
pub fn soundex(token: &str) -> String;
```

**Transition**: Python modules re-export Rust classes:

```python
# rigour/names/part.py
from rigour._core import NamePart, Span

# rigour/names/name.py
from rigour._core import Name

# rigour/names/symbol.py
from rigour._core import Symbol

# rigour/text/phonetics.py
from rigour._core import metaphone, soundex

# rigour/text/distance.py
from rigour._core import levenshtein, dam_levenshtein, jaro_winkler, levenshtein_similarity
```

**Dependency changes**: Drop `jellyfish` and `rapidfuzz` from `pyproject.toml`.

---

### Phase 3: Org Type Replacement + Prefix Removal

**Goal**: Port the `Replacer`/`Scanner` pattern and prefix removal to Rust.

**Rust implementation**:
- Org type data embedded from `resources/names/org_types.yml`
- `Replacer` using the `regex` crate with `\b...\b` Unicode word boundaries
- `remove_person_prefixes`, `remove_org_prefixes`, `remove_obj_prefixes`

**Regex engine choice**: Use the `regex` crate with Unicode `\b` word boundaries. This
replaces the Python `(?<!\w)...(?!\w)` pattern. The `regex` crate does not support
lookahead/lookbehind, but Unicode `\b` is semantically equivalent for our token types.
CJK characters are `\w` in both Python and the `regex` crate, so the CJK limitation
(boundaries don't fire between CJK characters) is preserved identically.

**Functions exposed via PyO3**:
- `replace_org_types_compare(text, normalizer_fn) -> str`
- `replace_org_types_display(text) -> str`
- `remove_org_types(text) -> str`
- `extract_org_types(text) -> list[str]`
- `remove_person_prefixes(text) -> str`
- `remove_org_prefixes(text) -> str`
- `remove_obj_prefixes(text) -> str`

**Key edge cases** (all must be test-covered):
- `compare: ""` entries — remove the match, don't substitute
- Dotted forms preserved by org type normalizer but stripped by `tokenize_name`
- Multi-word compound forms: `GmbH & Co. KG`
- CJK org types: `有限公司` etc.

---

### Phase 4: Aho-Corasick Tagger

**Goal**: Port the `Tagger` class and all data loading to Rust.

**Rust implementation**:
- `aho-corasick` crate (the same crate that the `ahocorasick-rs` Python package wraps)
- Tagger loads org symbols, domains, territories, person names from embedded data
- `word_boundary_matches` ported using `regex` crate for token boundary detection
- `tag_org_name`, `tag_person_name`, `_infer_part_tags` all in Rust

**The `Normalizer` callback goes away.** Currently `tag_org_name(name, normalizer)` and
`tag_person_name(name, normalizer)` take a Python callable. The normalizer is always
`normalize_name` in practice. Since `normalize_name` is now in Rust (Phase 1), the parameter
is unnecessary — Rust calls it directly. The Python-facing API can keep the parameter for
backwards compatibility but ignore it.

**Data loading**: All data (org symbols, domains, territories, ordinals, person names) is
embedded in the binary and parsed into `LazyLock`-initialized taggers on first access.
The person name corpus (~8.5MB) is zstd-compressed, decompressed on first use (~50-100ms).

**Thread safety**: The Python code protects tagger access with `resource_lock`. In Rust,
`LazyLock<Tagger>` is `Send + Sync` by default — no lock needed.

**Dependency removal**: Drop `ahocorasick-rs` from `pyproject.toml`.

---

### Phase 5: The analyze_names Pipeline

**Goal**: Single Rust function that takes flat input and returns tagged `Name` objects.
This is the coarse boundary crossing that makes the whole port worthwhile.

Python calls `analyze_names` once with a bag of strings; Rust runs the entire pipeline
(tokenization, transliteration, ASCII/metaphone computation, prefix removal, org type
replacement, Aho-Corasick tagging) and returns finished `Name` objects. No Python/Rust
boundary crossings during the hot loop.

**Python-facing API** (design TBD — may be keyword arguments, a dataclass, or a PyO3 class):

```python
# rigour/names/analysis.py
from rigour._core import _analyze_names

def analyze_names(
    names: list[str],
    type_tag: NameTypeTag,
    *,
    is_query: bool = False,
    first_name: list[str] | None = None,
    last_name: list[str] | None = None,
    middle_name: list[str] | None = None,
    father_name: list[str] | None = None,
    mother_name: list[str] | None = None,
) -> set[Name]:
    return set(_analyze_names(
        names, type_tag, is_query,
        first_name or [], last_name or [],
        middle_name or [], father_name or [],
        mother_name or [],
    ))
```

**Nomenklatura integration** (thin adapter, no Rust):

```python
# nomenklatura/matching/logic_v2/names/analysis.py
from rigour.names import analyze_names, NameTypeTag

def entity_names(type_tag, entity, prop=None, is_query=False) -> Set[Name]:
    if prop is not None:
        names = entity.get(prop, quiet=True)
    else:
        names = entity.get_type_values(registry.name, matchable=True)
    return analyze_names(
        names, type_tag,
        is_query=is_query,
        first_name=entity.get("firstName", quiet=True),
        last_name=entity.get("lastName", quiet=True),
        middle_name=entity.get("middleName", quiet=True),
        father_name=entity.get("fatherName", quiet=True),
        mother_name=entity.get("motherName", quiet=True),
    )
```

---

## Normality Subsumption

The dependency stack is: **normality → rigour → followthemoney → nomenklatura**.

Once Phase 1 is complete (ICU4X transliteration in Rust), rigour can begin dropping normality:

1. **rigour** implements all needed normality functionality in `rigour.text.*`:
   - `ascii_text`, `latinize_text` → `rigour._core` (Rust, Phase 1)
   - `squash_spaces`, `category_replace` → pure Python in `rigour.text.cleaning`
   - `WS`, `UNICODE_CATEGORIES`, `Categories` → `rigour.text.constants`
   - `stringify` → `rigour.text.stringify` (or keep `banal.stringify`)
   - `slugify`, `safe_filename` → `rigour.text.slugify` / `rigour.mime.filename`
2. **rigour** replaces all `from normality import X` with `from rigour.text import X`
3. **rigour** drops `normality` from `pyproject.toml`
4. **followthemoney** switches its normality imports to `rigour.text` (FTM already depends
   on rigour)
5. **nomenklatura** does the same
6. **normality** becomes unreferenced in the stack

The `ascii_text`/`latinize_text` step is blocked on Phase 1. Everything else (squash_spaces,
category_replace, WS, etc.) can be inlined as pure Python immediately.

---

## Rust Crate Dependencies

```toml
[package]
name = "rigour-core"
version = "1.8.0"
edition = "2024"
rust-version = "1.85"

[lib]
name = "rigour_core"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.24", features = ["extension-module"] }

# Transliteration (Phase 1)
icu = { version = "2", features = ["transliteration", "compiled_data"] }

# Unicode categories for tokenization (Phase 1)
unicode-general-category = "1"

# Phonetics (Phase 2) — same Rust crate backing the jellyfish Python package
jellyfish = "1"

# String distance (Phase 2) — Rust crate from the rapidfuzz author
rapidfuzz = "0.1"

# Regex for org type replacement (Phase 3)
regex = "1"

# Aho-Corasick for tagging (Phase 4)
aho-corasick = "1"

# Data embedding & deserialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"
zstd = "0.13"

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }

[profile.release]
lto = true
codegen-units = 1
opt-level = 3
strip = true
```

---

## Key Design Decisions & Rationale

### Why LRU caches go away

The Python codebase uses LRU caches extensively (65k entries for transliteration, 131k for
phonetics, 20k for tokenizer lookups, 2k for distance functions) to compensate for Python's
per-call overhead. In Rust, even the full ICU4X transliteration path is microseconds — the
cache lookup + hash computation would cost more than re-running the function.

The Python wrapper layer handles trivial fast-paths (e.g. `text.isascii()` before calling
Rust `ascii_text`), but does no result caching. This also eliminates the `reset.py`
cache-clearing machinery needed for long-lived processes.

LRU caches never live in Rust. They remain only in Python for the thin cases where a
Python-level check avoids crossing to Rust at all.

### Why eagerly compute derived properties

The previous experiment showed that per-attribute FFI calls are death by a thousand cuts.
By computing `ascii`, `comparable`, `metaphone`, `integer`, `latinize`, `numeric` at
`NamePart` construction time in Rust, we pay once and then attribute access from Python is
a simple field read (~50ns, same as any C extension attribute).

### Why `NamePart.tag` is mutable but other fields are not

The tagging pipeline (`tag_text`, `_infer_part_tags`) modifies `part.tag` after `Name`
construction. But no derived property depends on `tag`:
- `ascii` depends on `form` only
- `comparable` depends on `form`, `latinize`, `ascii`, `numeric` — not `tag`
- `metaphone` depends on `form`, `latinize`, `ascii` — not `tag`

So `tag` is `#[pyo3(get, set)]` while all other fields are `#[pyo3(get)]` only.

### Why Span owns cloned parts (not indices)

Rust ownership makes it awkward for `Span` to hold references to `NamePart` objects owned
by `Name.parts`. The previous plan stored `Vec<usize>` indices, but this breaks when Python
holds a `Span` object: it has no back-reference to its parent `Name` to resolve indices.

Since `NamePart` is `Clone` and small (~200 bytes heap data), `Span` owns copies of its
parts. This matches the current Python semantics (`self.parts = tuple(parts)`) and keeps
`Span` self-contained. Within the pure-Rust pipeline, an internal index-based representation
could be used as an optimization, converting to owned copies at the PyO3 boundary.

### Why Symbol.id is always String

`Symbol.id` was previously heterogeneous: `str` for most symbols (e.g. `"LLC"`, `"FINANCE"`)
but `int` for GeoNames person name IDs. This complicates the Rust type (`enum SymbolId`)
and the PyO3 boundary (`Union[str, int]`).

Decision: convert GeoNames numeric IDs to strings at data load time. The IDs are opaque
identifiers used for equality comparison — their type doesn't matter. This simplifies
`Symbol` to two fields: `category: SymbolCategory` and `id: String`.

### Why embed data in the binary

No file path resolution at runtime. No `importlib.resources`, no `__file__` hacks. The Rust
binary is self-contained. The person names corpus (8.5MB) compresses to ~2-3MB with zstd.
Total wheel size increase is acceptable for a server-side library.

### Why ICU4X over ICU4C bindings

ICU4C bindings (`rust_icu_*`) require system ICU at build time and create linking headaches
for wheel distribution. ICU4X compiles statically with data baked in. The transliteration
API is experimental but functional and actively maintained by the ICU team.

### Why jellyfish and rapidfuzz as Cargo dependencies

Both already exist as Rust crates:
- **`jellyfish`** crate on crates.io — this is the same Rust code that the `jellyfish` Python
  package (which uses PyO3) wraps. Using it as a Cargo dependency guarantees exact output
  parity with the current Python implementation.
- **`rapidfuzz`** crate on crates.io — maintained by the same author as the Python `rapidfuzz`
  package (which is C++). The Rust crate provides the same algorithms. Output parity for edge
  cases should be verified during Phase 2.

Using these as Cargo dependencies means the algorithms compile into our binary. The Python
packages are dropped from `pyproject.toml`, eliminating two native dependencies.

### Why `\b` word boundaries over lookaround

The `regex` crate doesn't support lookahead/lookbehind. Unicode `\b` is semantically
equivalent for the token types we match. The CJK limitation (CJK chars are `\w`, so `\b`
doesn't fire between them) matches the existing Python behavior exactly.

---

## Testing Strategy

### Rust-Native Tests (`cargo test`)

Each Rust module has `#[cfg(test)]` unit tests for the Rust-internal logic:
- Transliteration: test vectors from normality's test suite
- Tokenization: Unicode category edge cases, SKIP_CHARACTERS behavior
- Script detection: sample characters from each script
- Phonetics: verify jellyfish crate output matches Python jellyfish output
- String distance: verify rapidfuzz crate output matches Python rapidfuzz output
- Name construction: end-to-end from raw string to tagged Name with properties

### Python Integration Tests

All existing tests in `tests/` remain the primary validation. They exercise the PyO3 boundary
and catch any marshalling issues. New tests:
- `tests/text/test_transliteration.py`: comprehensive corpus with pinned expected outputs
- `tests/names/test_analysis.py`: tests for the `analyze_names` pipeline (Phase 5)

### Type Stubs (`rigour/_core.pyi`)

The `.pyi` file is a first-class deliverable, not an afterthought. Without it, `mypy --strict`
breaks for rigour and all downstream packages (FTM, nomenklatura, yente). It must be kept in
sync with every change to the PyO3 API.

### Benchmarks

Criterion benchmarks in `rust/benches/names.rs`:
- `tokenize_name` on 10k names from the person corpus
- `ascii_text` on multilingual name samples (Latin, Cyrillic, CJK, Arabic)
- `analyze_names` end-to-end on a batch of entity-like inputs
- Compare cold (first call, tagger initialization) vs warm (subsequent calls)

Python benchmarks (separate script, not in CI):
- Compare `entity_names()` before and after Rust migration on a real nomenklatura dataset

---

## Dependency Removal Roadmap

| Phase | Drop Python dependency | Replaced by Cargo dependency |
|-------|----------------------|------------------------------|
| 1 | `pyicu` | `icu` crate (ICU4X) |
| 1+ | `normality` | `rigour.text.*` (Rust + pure Python) |
| 2 | `jellyfish` | `jellyfish` crate |
| 2 | `rapidfuzz` | `rapidfuzz` crate |
| 4 | `ahocorasick-rs` | `aho-corasick` crate |
| — | `fingerprints` | Review if still needed after org_types port |

---

## Files to Create / Modify

### New files

- `rust/Cargo.toml` — Rust crate configuration
- `rust/Cargo.lock` — Rust dependency lock
- `rust/src/lib.rs` — PyO3 module definition
- `rust/src/text/mod.rs`, `transliterate.rs`, `scripts.rs`, `tokenize.rs`
- `rust/src/names/mod.rs`, `part.rs`, `name.rs`, `symbol.rs`, `span.rs`, `tag.rs`
- `rust/src/names/tagger.rs`, `org_types.rs`, `prefix.rs`, `analysis.rs`
- `rust/src/phonetics.rs`, `rust/src/distance.rs`
- `rust/data/` — JSON data files for embedding
- `rust/benches/names.rs` — Criterion benchmarks
- `rigour/text/transliteration.py` — public API for ascii_text, latinize_text
- `rigour/names/analysis.py` — analyze_names wrapper
- `rigour/_core.pyi` — type stubs for Rust extension
- `.github/workflows/build.yml` — updated CI with maturin-action

### Modified files

- `pyproject.toml` — maturin build backend, updated dependencies
- `rigour/text/scripts.py` — delegate to `_core`
- `rigour/names/tokenize.py` — delegate to `_core`, remove LRU caches
- `rigour/names/part.py` — re-export `_core.NamePart`, `_core.Span`
- `rigour/names/name.py` — re-export `_core.Name`
- `rigour/names/symbol.py` — re-export `_core.Symbol`
- `rigour/text/phonetics.py` — delegate to `_core`
- `rigour/text/distance.py` — delegate to `_core`
- `rigour/names/tagging.py` — delegate to `_core` (Phase 4)
- `rigour/names/org_types.py` — delegate to `_core` (Phase 3)
- `genscripts/` — extend to produce JSON for Rust embedding

### Removed files (eventually)

- `rigour-core/` — old experiment directory (clean up)
- `rigour/_core.cpython-313-darwin.so` — old experiment binary

---

## Open Questions

1. **ICU4X API verification**: The transliterator code snippets are illustrative. The exact
   API (`try_new` vs `try_new_with_compiled_data`, data provider pattern) needs verification
   against the `icu` crate v2 docs during Phase 1 implementation.

2. **ICU4X binary size**: The `compiled_data` feature includes CLDR data for all scripts.
   Need to measure actual binary size impact. If too large, `icu_datagen` can generate data
   for only the transliteration rules we need.

3. **`genscripts/` output format**: Deferred. Currently generates Python data files. Will
   need to also generate JSON (or similar) for Rust embedding. Exact mechanism TBD.

4. **`lru_cache` on `entity_names`**: Once `analyze_names` runs in Rust (Phase 5), the cache
   may be unnecessary — re-running the pipeline may be cheaper than Python cache overhead.
   Remove and benchmark.

5. **`rapidfuzz` Rust crate parity**: The Rust `rapidfuzz` crate is from the same author as
   the C++ Python package but is a separate implementation. Edge case output differences need
   to be tested during Phase 2.
