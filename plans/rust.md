---
description: Port rigour's name analysis pipeline and text primitives to Rust via rigour-core with ICU4X, PyO3, and maturin
date: 2026-04-19
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
   the same underlying Rust crates (`jellyfish`, `rapidfuzz`, `aho-corasick`) for the
   algorithms.
4. Reduce memory footprint: Python `Name`/`NamePart` objects cost ~1-5KB each; Rust structs
   cost ~200-400 bytes. For a nomenklatura index with 200k names, this is 200-1000MB vs 40-80MB

### Non-Goals

- Pure-Python fallback (all developers and CI must have a Rust toolchain)
- Porting the matching/scoring pipeline from nomenklatura (separate future work)
- Major version bump (will be 2.0 eventually, but only when explicitly decided)

### Windows support

The original plan excluded Windows because ICU4C bindings would have required shipping
ICU DLLs and debugging Windows linker/manifest issues. With the ICU4C → ICU4X pivot,
every dependency in the crate is pure Rust (`icu`, `jellyfish`, `rapidfuzz`,
`aho-corasick`, `regex`, `unicode-general-category`) or has first-class Windows support
(`pyo3`, `maturin-action`, `zstd` via MSVC). Adding Windows to the CI matrix is a
one-row change; no source code is Windows-aware. We ship `win_amd64` wheels for
Python 3.10–3.13. `win_arm64` is skipped until there is demand.

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
requires = ["maturin>=1.13,<2.0"]
build-backend = "maturin"

[tool.maturin]
features = ["pyo3/extension-module"]
module-name = "rigour._core"
manifest-path = "rust/Cargo.toml"
```

The switch from hatchling is a clean replacement — rigour's current `pyproject.toml`
doesn't use hatchling features beyond the default (no custom hooks, no version
plugins), so `build-backend` becomes a single-line change.

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
│   ├── src/generated/             # Generated .rs files (phf tables, sorted slices) — committed
│   │   ├── scripts.rs             # Unicode script ranges (sorted slice literal)
│   │   ├── ordinals.rs            # ordinal tables (phf::Map per lang)
│   │   ├── stopwords.rs           # stopwords/nullwords (phf::Set per lang)
│   │   └── prefixes.rs            # person/org name prefixes (&[&str])
│   ├── data/                      # Generated JSON(L) + zstd blobs — committed
│   │   ├── org_types.json
│   │   ├── org_symbols.json
│   │   ├── person_symbols.json
│   │   ├── territory_names.jsonl  # stripped territory subset for the tagger
│   │   └── persons.txt.zst        # zstd-compressed AC pattern list
│   └── benches/
│       └── names.rs               # Criterion benchmarks
├── rigour/                        # Python package (unchanged structure)
│   ├── _core.pyi                  # Type stubs for the Rust extension (REQUIRED for mypy)
│   ├── data/                      # PARTIALLY preserved — Python-side consumers remain
│   │   ├── territories/           # kept: full territory records, read by rigour.territories
│   │   ├── langs/                 # kept: ISO639 tables, read by rigour.langs
│   │   ├── addresses/             # kept: address formats, read by rigour.addresses
│   │   └── text/ordinals.py       # kept: also consumed by addresses/normalize.py
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
├── resources/                     # Source YAML/text files (unchanged — canonical human input)
├── genscripts/                    # Generation scripts (extended to emit JSON/JSONL/zstd/.rs for Rust)
├── Makefile                       # `make rust-data` target — regenerates all Rust-consumed artifacts
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
| Windows | x86_64 | 3.10-3.13 | win_amd64 |

Source distribution (`sdist`) also published for `pip install` from source (requires Rust
toolchain + maturin).

---

## ICU4X for Transliteration

*Updated with ICU4X spike results (April 2026). See `spikes/icu4x-spike/` for the code.*

### Why ICU4X Instead of ICU4C

The previous attempt used `rust_icu_utrans` which wraps ICU4C via bindgen. Problems:
- Requires ICU4C headers and libraries at build time
- Creates linking headaches for manylinux wheel distribution (must bundle or static-link ICU)
- The Python→Rust→ICU4C double-hop didn't outperform Python→ICU4C (PyICU) directly

**ICU4X** (`icu` crate v2.2.0) is the ICU team's pure-Rust rewrite. Advantages:
- Compiles statically, no system dependency
- Data baked into the binary (CLDR data via `compiled_data` feature)
- Binary size with all transliteration data: **3.4 MB**
- Init time for all transliterators: **<1ms**

### Transliteration Architecture (Spike-Validated)

ICU4X `compiled_data` does NOT include `Any-Latin` (the compound transliterator used by
PyICU). It DOES include 10 script-specific transliterators. The architecture is a manual
pipeline with script detection:

```rust
use icu::experimental::transliterate::Transliterator;
use icu::normalizer::DecomposingNormalizerBorrowed;
use icu::properties::{CodePointMapDataBorrowed, props::GeneralCategory};

// Step 1: Script-specific transliterators (built-in compiled_data)
// Only the one matching the input script is applied.
let cyrl: Transliterator = Transliterator::try_new(
    &"und-Latn-t-und-cyrl".parse().unwrap()
).unwrap();

// Step 2: NFKD + mark removal (direct normalizer API — 3.5M ops/sec)
let nfkd = DecomposingNormalizerBorrowed::new_nfkd();
let gc: CodePointMapDataBorrowed<GeneralCategory> = CodePointMapDataBorrowed::new();

pub fn ascii_text(input: &str) -> String {
    if input.is_ascii() { return input.to_string(); }

    let mut s = input.to_string();

    // 1. Apply script-specific transliterator (only if non-Latin detected)
    let scripts = detect_scripts(input);
    for script_key in &scripts {
        if let Some(t) = SCRIPT_TRANS.get(script_key) {
            s = t.transliterate(s);
        }
    }

    // 2. NFKD decomposition + remove nonspacing marks (replaces Latin-ASCII)
    let decomposed = nfkd.normalize_utf8(s.as_bytes());
    s = decomposed.chars()
        .filter(|c| gc.get(*c) != GeneralCategory::NonspacingMark)
        .collect();

    // 3. Custom ASCII fallback for non-decomposable chars (ø→o, ß→ss, ə→a, etc.)
    s = ascii_fallback_table(&s);

    s
}
```

Available built-in transliterators (BCP-47-T locale IDs):

| Locale ID | Script | Spike-verified |
|-----------|--------|----------------|
| `und-Latn-t-und-cyrl` | Cyrillic | Yes — exact match |
| `und-Latn-t-und-arab` | Arabic | Yes — exact match |
| `und-Latn-t-und-hans` | Chinese (Simplified) | Yes — exact match |
| `und-Latn-t-und-grek` | Greek | Yes — exact match |
| `und-Latn-t-und-hang` | Hangul | Yes — exact match |
| `und-Latn-t-und-geor` | Georgian | Yes — exact match |
| `und-Latn-t-und-armn` | Armenian | Yes — minor variant |
| `und-Latn-t-und-deva` | Devanagari | Yes (untested in corpus) |
| `und-Latn-t-und-kana` | Katakana | Yes — exact match |
| `und-Latn-t-und-hebr` | Hebrew | Yes (untested in corpus) |

### Threading: `Transliterator` is `!Send`/`!Sync`

Cannot use `std::sync::LazyLock`. Options:
- `thread_local!` with `RefCell` — simplest, works with PyO3 GIL guarantee
- Per-call construction — too slow (~900µs init)
- `unsafe impl Send` — risky, transliterator may hold Rc internally

Recommended: `thread_local!` since Python's GIL means one thread per interpreter.

### Spike Output Quality: 40/45 exact matches

| Difference | PyICU | ICU4X | Verdict |
|-----------|-------|-------|---------|
| Norwegian ø | `Lo/kke` | `Lokke` | ICU4X better |
| Azeri ə/Ə | `ahmad` | `?hm?d` | Fix: add to ASCII fallback table |
| Armenian w/v | `Geworg` | `Gevorg` | Both valid romanizations |
| Georgian apostrophe | curly `'` (U+2019) | ASCII `'` (U+0027) | ICU4X correct for ASCII |

**Latinize: 5/5 exact matches** (Ukrainian, Russian, Greek, Chinese, Georgian).

### Performance: Bottleneck Identified and Solved

The `Latin-ASCII` built-in transliterator is 4,500 ops/sec — a bottleneck. Replace with
direct `icu::normalizer` (3.5M ops/sec) + custom fallback table.

| Step | ops/sec | Production approach |
|------|---------|-------------------|
| Script transliterator | 52,000 | Keep (built-in) |
| NFKD + Mn removal | 3,500,000 | Use `DecomposingNormalizerBorrowed` directly |
| ASCII fallback | ~millions | Custom lookup table |
| Latin-ASCII (built-in) | 4,500 | **DO NOT USE** — replaced by above |

### Cargo Dependencies

```toml
[dependencies]
icu = { version = "2", features = ["unstable", "compiled_data"] }
```

Feature `unstable` gates `icu::experimental::transliterate`. Feature `compiled_data` bakes
CLDR data into the binary.

### Test Expectations to Update

When switching from PyICU to ICU4X, these pinned test values will change:
- Norwegian: `"Lars Lo/kke Rasmussen"` → `"Lars Lokke Rasmussen"` (improvement)
- Georgian: curly apostrophe → ASCII apostrophe (correction)

**Goal: drop `pyicu` from rigour's dependencies once ICU4X transliteration is in place.**

---

## Data Embedding Strategy

All resource data compiled into the Rust binary. No runtime file I/O for data loading.

### Source-of-truth vs. generated artifact (incremental migration)

The YAML/text files in `resources/` remain the canonical, human-edited source of truth —
nothing in this plan changes them. What changes, dataset-by-dataset, is *which
consumer format `genscripts/` emits* and *who reads it*. Migration is driven by the
Rust pipeline's needs, not by a goal of unifying the data layer. Datasets that only
Python ever reads stay Python-consumed.

**In scope (datasets the name-analysis pipeline needs; migrated in step with their
Phase):**

| Current Python consumer | Dataset | Rust-owned from | Current location |
|------------------------|---------|------------------|------------------|
| `names/org_types.py` | `ORG_TYPES` | Phase 3 | `rigour/data/names/org_types.py` |
| `names/tagging.py`, `names/pick.py` | Symbols, domains, nicks, scripts, name parts | Phase 4 | `rigour/data/names/data.py`, `rigour/data/text/scripts.py` |
| `names/tagging.py` | Person name corpus (persons.txt) | Phase 4 | `rigour/data/names/persons.txt` |
| `names/prefix.py`, `names/split_phrases.py` | Prefix lists, split phrases | Phase 3 | `rigour/data/names/data.py` |
| `names/check.py` | `GENERIC_PERSON_NAMES` | Phase 4 | `rigour/data/names/data.py` |
| `text/scripts.py` | Script ranges, Latin char sets | Phase 1 | `rigour/data/text/scripts.py` |
| `text/stopwords.py` | Stopwords, nullwords, nullplaces | Phase 4 (when pipeline needs them) | `rigour/data/text/stopwords.py` |
| `names/tagging.py` (+ `addresses/normalize.py`) | Ordinals | Phase 4 — but see below | `rigour/data/text/ordinals.py` |
| `names/tagging.py` (+ `territories/*`) | Territory *name aliases* (stripped subset) | Phase 4 — but see below | derived from `rigour/data/territories/data.jsonl` |

The focus is **name symbols and org types** — those are the Rust pipeline's
substantive data dependencies. Everything else listed above follows because the
pipeline touches it, not because we're trying to move data for its own sake.

**Out of scope — full records stay Python-only:**

- **Territories** (`rigour/data/territories/data.jsonl`) — the full record with QID,
  parent, ISO codes, jurisdiction flags, summaries, etc. is consumed by
  `rigour.territories.*` for lookup and resolution. The full dataset stays
  Python-only for the foreseeable future. But see "Shared data: territory names" below
  — the name-alias subset is also consumed by the Rust tagger.
- **ISO639 language tables** (`rigour/data/langs/iso639.py`) — `langs/*` consumers only.
- **Address formats** (`rigour/data/addresses/*`) — `addresses/*` consumers only.

The genscript entrypoints for the out-of-scope-in-full datasets (`generate_langs.py`,
`generate_addresses.py`) are untouched. `generate_territories.py` is touched only to
emit one additional artifact (see below) — the existing JSONL output is unchanged.

**Shared data: two sources, two consumers, two artifacts**

Two datasets are legitimately needed on both sides of the language boundary. The
pattern in both cases: `genscripts/` emits *two* artifacts from one source, each
shaped for its consumer. No cross-language coupling; a PR that edits the source
regenerates both.

- **Ordinals**. Consumed by `names/tagging.py` (→ Rust) and `addresses/normalize.py`
  (→ Python). `genscripts/` keeps emitting `rigour/data/text/ordinals.py` for the
  address code *and* emits a parallel Rust-consumable artifact. ~90KB of duplication.
- **Territory name aliases**. Consumed by `names/tagging.py` for the `LOCATION`
  symbol category (see `rigour/names/tagging.py:112–120` — it pulls `code`, `name`,
  `full_name`, `names_strong` per territory) *and* by `rigour.territories.*` for the
  full territory database. `generate_territories.py` keeps emitting the full
  `rigour/data/territories/data.jsonl` as today *and* emits a stripped
  `rust/data/territory_names.jsonl` with just the tagger-relevant fields
  (~100–200KB). The Rust tagger loads the stripped file; the Python territory API
  keeps using the full file. Regeneration of both is enforced by the same
  `make rust-data` target + CI no-diff check.

The "clean up via `_core` round-trip back to Python" option (Rust owns the data,
Python reads through the extension) is deferred for both — dual-artifact duplication
is simpler now and doesn't paint us into a corner later.

**What gets deleted, when**

The corresponding `rigour/data/<file>.py` is deleted *only once the Rust port of its
one consumer lands and the generator stops emitting it*. Order follows the phase
plan: `scripts.py` goes in Phase 1; `org_types.py` in Phase 3; `data.py` (split into
its various tag-bearing exports) in Phase 4; `ordinals.py` may never go away because
of the address-code consumer. We are not aiming for a sweep of `rigour/data/`.

### Format choice: right tool per dataset

JSON is a defensible default, but "JSON everywhere" leaves three optimisations on the
table. The plan uses three formats, each matched to what the dataset *does* at runtime.

#### Tier 1: Compressed pattern list, rebuild on first use (person name corpus)

`persons.txt` feeds an Aho-Corasick automaton with ~150k patterns. An earlier draft of
this plan proposed precomputing the automaton in `genscripts/` and embedding the
serialised DFA bytes. **That approach does not work**: the `aho-corasick` crate v1.x
exposes neither serde support nor raw byte serialisation (verified against its v1
API — the `AhoCorasick` struct holds a `Arc<dyn AcAutomaton>` and has no
`to_bytes`/`from_bytes` analogues to what `regex-automata` provides for its DFAs).
Implementing cross-platform serialisation ourselves would be fragile and tied to the
crate's private representation.

Plan of record: ship the patterns as a zstd-compressed text blob
(`rust/data/persons.txt.zst`, ~2–3MB compressed from 8.5MB), `include_bytes!` the
blob, and build the automaton inside a `LazyLock<AhoCorasick>` on first tagger access.
This pays the construction cost once per process at first use. Rough expected cost is
50–200ms; precise figure to be measured during Phase 4. For long-lived consumers
(yente, zavod, nomenklatura indexing) this is negligible; for short-lived CLI
invocations that hit the tagger it's the dominant startup cost.

**Mitigation if the measured cost is intolerable**: evaluate `daachorse` (a
double-array Aho-Corasick implementation whose explicit goal is compact, serialisable
automata), with parity testing against `aho-corasick` for word-boundary matching,
overlapping vs leftmost-first semantics, and case sensitivity behaviour. Treat this as
an optimisation pass after Phase 4 benchmarks, not a Phase 0 commitment.

#### Tier 2: Generated `.rs` files with sorted-slice literals (static lookup tables)

The Unicode script ranges, Latin/Latinizable character sets, ordinal tables, stopwords,
and name prefix lists are small static maps and range tables (all under a few thousand
entries). In Python they live as `Dict[int, Tuple[str, ...]]` literals parsed at
import time (`ordinals.py` is 89KB of generated Python for this reason).

The Rust approach: `genscripts/` emits a `.rs` file containing a sorted
`&'static [(K, V)]` or `&'static [(u32, u32, Script)]` range array. The file is
committed to `rust/src/generated/` and the Rust compiler bakes the data directly into
the binary. Lookup is `slice::binary_search_by_key` — the compiler inlines it, and for
our sizes it's competitive with perfect hashing while being vastly simpler to generate
from Python (no hash-function coordination, just sort + format a literal).

No runtime parse, no allocation, no `LazyLock`, compiler-checked structure. If a
specific lookup becomes a measured hot spot and sorted-slice search isn't fast enough,
that single case can switch to `phf` later as an optimisation — but it's not a default.

#### Tier 3: JSON(L) inside `LazyLock` (structured records)

Org types, territories, org symbols/domains, person symbols/nicks. Few hundred to few
thousand entries with nested optional fields. Parse cost is sub-millisecond so there's
no win from binary formats, and the JSON is human-inspectable if someone needs to diff
a regeneration. `include_str!` + `serde_json::from_str` inside `LazyLock`. The YAML
source stays as the human-edited form; JSON is just the build artifact Rust consumes.

#### Formats explicitly rejected

- **bincode / postcard / rkyv across the board**: compact and fast to deserialise, but
  diff-hostile and adds a debugging tax when a dataset looks wrong. Zero-copy is
  alluring but none of this data is in the hot path after init — the cost after
  deserialisation is what matters, and there all formats are equivalent.
- **MessagePack**: same tradeoff as bincode, no real benefit over JSON at these sizes.
- **YAML at runtime (`serde_yaml`)**: unnecessary dependency and slower than JSON;
  convert to JSON in `genscripts/` instead.
- **Embedding raw Python source and parsing it from Rust**: obvious no, mentioned only
  to close off the "can we just keep `rigour/data/*.py`?" question.

### Sources and Embedding

| Resource | Upstream source | Format → | Loaded via |
|----------|----------------|----------|-------------|
| Person name corpus | `resources/names/names/*.gz` | `persons.txt.zst` (zstd-compressed patterns) | `include_bytes!` + zstd decode + `AhoCorasick::new` in `LazyLock` |
| Unicode script ranges | Unicode data via genscripts | `scripts.rs` (sorted range slice) | Compiled-in `static` |
| Latin/Latinizable chars | Unicode data via genscripts | `latin.rs` (sorted range slice) | Compiled-in `static` |
| Ordinals | `resources/text/ordinals.yml` | `ordinals.rs` (sorted slice) | Compiled-in `static` |
| Stopwords, nullwords | `resources/text/stopwords.yml` | `stopwords.rs` (sorted slice per lang) | Compiled-in `static` |
| Person name prefixes | `resources/names/prefixes.yml` | `prefixes.rs` (slice of `&str`) | Compiled-in `static` |
| Org types | `resources/names/org_types.yml` | `org_types.json` | `include_str!` + serde in `LazyLock` |
| Org symbols, domains | `resources/names/symbols.yml` | `org_symbols.json` | `include_str!` + serde in `LazyLock` |
| Person symbols, nicks | `resources/names/symbols.yml` | `person_symbols.json` | `include_str!` + serde in `LazyLock` |
| Territory name aliases | `resources/territories/` (stripped subset — `{code, name, full_name, names_strong}`) | `territory_names.jsonl` | `include_str!` + line-by-line serde in `LazyLock` |

### Genscripts stays Python

`genscripts/` continues to be Python. The generators use the Python ecosystem
(Wikidata client, unidecode, existing rigour utilities), run rarely (at release prep,
not on every build), and rewriting them in Rust would be disproportionate effort for a
~620-line codebase that already works. The clean split is: **Python generates, Rust
consumes**. A top-level `make rust-data` target regenerates everything under `rust/`
and `rust/src/generated/`; committed artifacts are the contract between the two
languages. CI checks that a fresh `make rust-data` produces no diff against what's
committed.

### Lazy Initialization — the idiomatic `@cache` equivalent

The Python codebase uses no-argument `@cache` extensively to build process-lifetime
singletons (compiled regexes, loaded YAML, Aho-Corasick taggers). The direct Rust
equivalent is `std::sync::LazyLock<T>` at module scope:

```rust
use std::sync::LazyLock;

static ORG_TYPE_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    let data = include_str!("../data/org_types.json");
    Regex::new(&build_pattern(data)).unwrap()
});

static NAME_TAGGER: LazyLock<AhoCorasick> = LazyLock::new(|| {
    let bytes = include_bytes!("../data/persons.txt.zst");
    AhoCorasick::new(parse_patterns(&zstd::decode_all(&bytes[..]).unwrap())).unwrap()
});
```

Properties: first-access lazy init, thread-safe via an atomic once-flag, held for the
process lifetime, no synchronisation cost on subsequent reads. `LazyLock<T>: Sync` when
`T: Sync`, so no `resource_lock` equivalent is needed. Stable since Rust 1.80 (we pin
1.85).

**Exception for `!Send`/`!Sync` types**: ICU4X `Transliterator` holds `Rc` internally
and cannot go in a `static`. Those use `thread_local!` with a `RefCell`. Under the GIL
this is effectively a process-lifetime singleton; each interpreter thread pays init
once. See "Threading: `Transliterator` is `!Send`/`!Sync`" above.

**Not carried over from Python**: the `@lru_cache(maxsize=N)` memoization on
transliteration, phonetics, distance, and tokenizer lookups — see "Why LRU caches go
away" below. That also makes `rigour/reset.py`'s `cache_clear()` machinery obsolete:
`LazyLock` and `thread_local!` have no reset API, but neither do these singletons need
invalidation (they're derived from embedded data that never changes at runtime).

---

## Phased Implementation

### Phase 0: Test Corpus + Feasibility Spikes

**Goal**: De-risk Phase 1 by expanding test coverage (so we can detect regressions when
swapping in Rust) and validating that ICU4X and maturin work for our use case.

**Test corpus expansion**: DONE (306 tests, mypy clean)

- Transliteration: 33 test functions pinning `ascii_text`/`latinize_text` across all 21 target
  languages, mixed scripts, org names. File: `tests/text/test_transliteration.py`
- Tokenization: 13 new test functions for language-specific tokenization, punctuation edge
  cases, Unicode categories, KEEP_CHARACTERS. File: `tests/names/test_tokenize.py`
- Script detection: 11 new test functions covering previously untested languages and boundary
  codepoints. File: `tests/text/test_scripts.py`
- Bugs fixed: Japanese ー deletion (KEEP_CHARACTERS), Burmese Mc splitting (category fix)

**ICU4X spike**: DONE — verdict: **CONDITIONAL GO**

- Code: `spikes/icu4x-spike/`
- `icu` crate v2.2.0, features `["unstable", "compiled_data"]`
- `Any-Latin` compound transliterator NOT in compiled_data — use manual pipeline instead
  (script detection → targeted built-in transliterator → NFKD normalizer → ASCII fallback)
- 40/45 exact ASCII matches, 5/5 exact latinize matches
- Binary: 3.4 MB, init: <1ms
- `Transliterator` is `!Send`/`!Sync` — use `thread_local!`
- Bottleneck: `Latin-ASCII` built-in (4.5K ops/sec) — replace with direct normalizer (3.5M ops/sec)
- See "ICU4X for Transliteration" section above for full details

**Maturin spike**: TODO

- Create a minimal `rust/Cargo.toml` + `rust/src/lib.rs` with a single PyO3 function
  (e.g. `fn hello() -> &str`)
- Switch `pyproject.toml` build-backend from hatchling to maturin (clean replacement —
  rigour's current hatchling usage is default-only, no custom hooks)
- Verify: `maturin develop` works, `pip install -e .` works, `import rigour._core` works,
  existing tests still pass, `mypy --strict` still passes with a `.pyi` stub
- Test the CI pipeline: maturin-action builds wheels for at least one platform
- Verify Windows build too (one matrix entry) — first real test of the newly-in-scope target

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

**Data embedded** (Tier 2 — committed sorted-slice `.rs` literals in `rust/src/generated/`):
Unicode script ranges (`scripts.rs`), Latin/Latinizable character sets (`latin.rs`).

**New files**:
- `rust/Cargo.toml`, `rust/src/lib.rs`
- `rust/src/text/mod.rs`, `transliterate.rs`, `scripts.rs`, `tokenize.rs`
- `rust/src/generated/scripts.rs`, `latin.rs` — generated sorted-slice data
- `rigour/text/transliteration.py`
- `rigour/_core.pyi` — type stubs (**required**, without these mypy breaks for all downstream)
- `Makefile` with `rust-data` target driving `genscripts/`
- `.github/workflows/build.yml` — updated CI with maturin-action + `make rust-data` no-diff check

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
jellyfish = "1"      # metaphone, soundex
rapidfuzz = "0.5"    # levenshtein, damerau-levenshtein, jaro-winkler
```

An earlier revision of this plan tried to collapse these into one crate (jellyfish
alone covers all five algorithms we use). We reverted because `jellyfish` implements
distance algorithms as naive O(N·M) dynamic programming, while `rapidfuzz` implements
them as bit-parallel Myers/Hyyrö/Mbleven dispatch — **3–10× faster for our typical
name-length inputs** (5–50 chars fit in a single 64-bit word), even more on batches.
The whole point of this port is performance; shipping slower distance functions would
be backwards.

Both `jellyfish` (Python package) and `rapidfuzz` (Python package) are backed by
native code:
- **jellyfish**: Rust + PyO3. The `jellyfish` crate on crates.io is the same code.
  Output parity for metaphone/soundex is inherent.
- **rapidfuzz**: C++ Python package, but the same author maintains a `rapidfuzz` Rust
  crate on crates.io (verified: same three-tier algorithmic dispatch as the C++
  core, not a simplified port). Output parity against the Python rapidfuzz values
  currently used should still get a Phase 2 test sweep — same algorithms,
  independent implementations.

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
    // Collapses shorter name variants into longer ones they are contained in.
    // Return type is whatever idiomatic Rust collection satisfies the semantics —
    // likely Vec<Name> since deduplication is by `contains()`, not strict equality,
    // so HashSet would require a non-trivial Hash impl that's not actually needed.
    #[staticmethod]
    fn consolidate_names(names: Vec<Name>) -> Vec<Name>;
}
```

**Phonetics** — wrappers around `jellyfish`:

```rust
#[pyfunction]
pub fn metaphone(token: &str) -> String;
#[pyfunction]
pub fn soundex(token: &str) -> String;
```

**String distance** — wrappers around `rapidfuzz`:

```rust
#[pyfunction]
pub fn levenshtein(left: &str, right: &str, max_edits: Option<usize>) -> usize;
#[pyfunction]
pub fn dam_levenshtein(left: &str, right: &str, max_edits: Option<usize>) -> usize;
#[pyfunction]
pub fn jaro_winkler(left: &str, right: &str) -> f64;
#[pyfunction]
pub fn levenshtein_similarity(left: &str, right: &str, max_edits: usize, max_percent: f64) -> f64;
```

`rapidfuzz` supports `score_cutoff` natively on its distance functions, so `max_edits`
maps cleanly to that — we get the algorithmic early-exit instead of a hand-rolled
loop wrapper.

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

**Dependency changes**: Drop `jellyfish` and `rapidfuzz` from `pyproject.toml` —
both are now internal Cargo dependencies inside `rigour._core`. `territories/lookup.py`
also loses its direct `rapidfuzz` import and uses the `_core.levenshtein` wrapper
instead.

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
- Tagger loads org symbols, domains, territory name aliases (stripped subset),
  ordinals, and the person name corpus from embedded data — see the "Sources and
  Embedding" table in the Data Embedding Strategy section for the per-dataset format
- `word_boundary_matches` ported using `regex` crate for token boundary detection
- `tag_org_name`, `tag_person_name`, `_infer_part_tags` all in Rust

**The `Normalizer` callback goes away.** Currently `tag_org_name(name, normalizer)` and
`tag_person_name(name, normalizer)` take a Python callable. The normalizer is always
`normalize_name` in practice. Since `normalize_name` is now in Rust (Phase 1), the parameter
is unnecessary — Rust calls it directly. The Python-facing API can keep the parameter for
backwards compatibility but ignore it.

**Person name corpus loading**: see "Tier 1: Compressed pattern list" in the Data
Embedding Strategy section. First tagger access pays ~50–200ms for zstd decompression
plus AC automaton construction; subsequent calls hit the `LazyLock`.

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

Versions below are as of April 2026 (verified against crates.io). MSRV is 1.86
(required by `icu` 2.2 and `criterion` 0.8).

```toml
[package]
name = "rigour-core"
version = "1.8.0"
edition = "2024"
rust-version = "1.86"

[lib]
name = "rigour_core"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.28", features = ["extension-module"] }

# Transliteration (Phase 1) — "unstable" gates icu::experimental::transliterate,
# "compiled_data" bakes CLDR data into the binary
icu = { version = "2.2", features = ["unstable", "compiled_data"] }

# Unicode categories for tokenization (Phase 1)
unicode-general-category = "1"

# Phonetics (Phase 2) — metaphone, soundex. The jellyfish crate also provides
# Levenshtein/Damerau-Levenshtein/Jaro-Winkler, but we use rapidfuzz for those (see
# below) because jellyfish uses naive O(N·M) DP while rapidfuzz uses bit-parallel
# Myers/Mbleven algorithms that are 3–10× faster for our typical name-length inputs.
# NOTE: jellyfish crate has not seen a release since June 2023 (v1.0.0). API is
# stable; metaphone/soundex don't evolve; tolerable risk.
jellyfish = "1"

# String distance (Phase 2) — bit-parallel Levenshtein, Damerau-Levenshtein,
# Jaro-Winkler. Full Rust port of the rapidfuzz C++ core by the same author, same
# three-tier dispatch (Mbleven / Hyyrö / block-wise).
# NOTE: last release December 2023 (v0.5.0), pre-1.0, dormant. Acceptable because:
# (a) the algorithms don't change, (b) the API surface we use is tiny (3 functions),
# (c) the 3–10× performance advantage over jellyfish's DP implementation is load-
# bearing for the whole port's speed case. See Open Questions for fallback plan.
rapidfuzz = "0.5"

# Regex for org type replacement (Phase 3)
regex = "1"

# Aho-Corasick for tagging (Phase 4)
aho-corasick = "1"

# Data embedding & deserialization
serde = { version = "1", features = ["derive"] }
serde_json = "1"
zstd = "0.13"

[dev-dependencies]
criterion = { version = "0.8", features = ["html_reports"] }

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

### Why jellyfish AND rapidfuzz (not just one)

Both crates expose the core algorithms rigour uses, and it's tempting to collapse to
one dependency. We don't, because the implementations have materially different
performance:

- `jellyfish` implements Levenshtein, Damerau-Levenshtein, and Jaro-Winkler with
  straightforward O(N·M) dynamic programming (verified by reading
  `src/levenshtein.rs`, `damerau_levenshtein.rs`, `jaro.rs` in the crate source).
- `rapidfuzz` uses bit-parallel algorithms: Myers/Hyyrö 2003 for Levenshtein on
  strings that fit in 64 bits, Mbleven pruning for low-edit-distance short strings,
  block-wise with Ukkonen band for longer inputs. For our typical 5–50 character
  name inputs, Levenshtein fits in a single machine word and runs **3–10× faster**
  than a DP matrix (more on batches).

Because the whole point of this port is speed, we take the faster implementation for
distance functions. `jellyfish` stays for metaphone and soundex (rapidfuzz doesn't
have those). Having two small Rust crates compiled into one `.so` is essentially
free at the Python boundary — there's no performance cost to keeping both.

The Rust `rapidfuzz` crate (0.5.0, December 2023) is a full algorithmic port of the
C++ core by the same author, not a simplified port — same three-tier dispatch, same
published complexity bounds. Dormant since late 2023 but the algorithms don't evolve;
API surface we use is three functions.

Distance output parity against the current Python `rapidfuzz` values should still be
verified in Phase 2 (independent implementations of well-specified algorithms should
agree, but worth confirming concretely).

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
| 2 | `jellyfish` | `jellyfish` crate (metaphone, soundex) |
| 2 | `rapidfuzz` | `rapidfuzz` crate (bit-parallel distance, 3–10× faster than jellyfish DP) |
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
- `rust/src/generated/` — committed `.rs` files with sorted-slice literals (Tier 2)
- `rust/data/` — committed JSON/JSONL/zstd artifacts (Tier 1 + Tier 3)
- `rust/benches/names.rs` — Criterion benchmarks
- `Makefile` — `make rust-data` target driving `genscripts/`; CI runs it and fails on diff
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
- `genscripts/generate_names.py` — emit JSON (org_types, symbols) and zstd (persons.txt) for Rust
- `genscripts/generate_text.py` — emit sorted-slice `.rs` for scripts, stopwords, ordinals
- `genscripts/generate_territories.py` — emit stripped `territory_names.jsonl` alongside existing full JSONL

### Removed files (incremental, per phase)

- `rigour/data/text/scripts.py` — Phase 1 (replaced by Rust `scripts.rs`)
- `rigour/data/names/org_types.py` — Phase 3 (replaced by `rust/data/org_types.json`)
- `rigour/data/names/data.py` — Phase 4 (split across Rust JSON + generated `.rs`)
- `rigour/data/text/stopwords.py` — Phase 4 (replaced by Rust `stopwords.rs`)
- `rigour-core/` — old experiment directory (clean up)
- `rigour/_core.cpython-313-darwin.so` — old experiment binary

Note: `rigour/data/text/ordinals.py`, `rigour/data/territories/data.jsonl`,
`rigour/data/langs/iso639.py`, `rigour/data/addresses/*` are **not** removed — they
retain Python-side consumers indefinitely. See "Source-of-truth vs. generated
artifact" for rationale.

---

## Open Questions

1. **ICU4X API verification**: The transliterator code snippets are illustrative. The exact
   API (`try_new` vs `try_new_with_compiled_data`, data provider pattern) needs verification
   against the `icu` crate v2.2 docs during Phase 1 implementation.

2. **`rapidfuzz` Rust crate maintenance status**: v0.5.0, last release December 2023.
   Pinned dependency risk: if a bug appears, we can't just update. Acceptable because
   (a) the three functions we use (Levenshtein, Damerau-Levenshtein, Jaro-Winkler)
   are well-specified and bug-stable, (b) the crate source is the full algorithmic
   port of the C++ rapidfuzz, not a toy version, and (c) the performance advantage
   over alternatives is load-bearing. Fallback if the crate actually breaks: pin to a
   git SHA and maintain a fork, or port the ~300 lines of Myers/Mbleven we actually
   need. Neither is catastrophic.

3. **`jellyfish` Rust crate maintenance status**: Last release June 2023 (v1.0.0).
   1.0 implies API stability; metaphone/soundex don't evolve. Tolerable risk. No
   action needed unless a CVE surfaces.

4. **Distance-function output parity**: Phase 2 should pin current Python
   `rapidfuzz`-computed distances on a corpus of a few hundred string pairs and verify
   the Rust `rapidfuzz` crate produces identical results. Same algorithms, independent
   implementations — should agree, but worth confirming concretely.

5. **`lru_cache` on `entity_names`**: Once `analyze_names` runs in Rust (Phase 5), the cache
   may be unnecessary — re-running the pipeline may be cheaper than Python cache overhead.
   Remove and benchmark.

6. **Person tagger startup cost**: Estimated 50–200ms for zstd decode + AC construction on
   first tagger access; precise figure to be measured during Phase 4. If intolerable,
   evaluate `daachorse` (see Tier 1 in Data Embedding Strategy).

7. **Free-threaded Python (PEP 703 / `python3.13t`)**: The `thread_local!` pattern
   for ICU4X relies on Python's GIL enforcing effectively one interpreter thread.
   Under free-threaded builds, each OS thread pays transliterator init separately
   (~900µs). Decision needed in Phase 1: build `abi3` wheels only (freeze out
   free-threaded adopters) or add `cp313t`/`cp314t` wheels to the matrix. No action
   blocking Phase 0.

8. **`analyze_names` API shape (Phase 5)**: kwargs function vs `#[pyclass] AnalyzeRequest`.
   Lean toward the pyclass: type-safe, extensible (nationalities/aliases are plausible
   next fields), and nomenklatura's call site is the only consumer so the ergonomic
   cost is paid once.

### Resolved

- **Build backend switch**: plain replacement of hatchling with maturin. rigour's
  current `pyproject.toml` uses hatchling at default settings only, so no migration
  friction.
- **Wheel size**: not a concern. Current rigour wheel ships `persons.txt` at ~8.5MB
  uncompressed; zstd-compressing it to ~2–3MB and adding ICU4X's 3.4MB is net-neutral
  to net-smaller than today.
- **`consolidate_names` return type**: no hashing spec needed. Semantics are
  collapse-shorter-into-longer by `contains()` relation, so `Vec<Name>` is the
  idiomatic return — `HashSet<Name>` would force a `Hash`/`Eq` impl the semantics
  don't actually need.
- **ICU4X binary size**: measured at 3.4MB for all transliteration data (spike,
  April 2026). Within budget; no need to trim via `icu_datagen`.
- **`genscripts/` output format**: resolved by the three-tier format strategy in the
  Data Embedding section. Genscripts stays Python, emits JSON/JSONL/zstd into
  `rust/data/` and sorted-slice `.rs` literals into `rust/src/generated/`, regenerated
  via `make rust-data` with a CI no-diff check.
- **Versions of all Rust crates and build tools**: pinned to current latest stable
  as of April 2026. See "Rust Crate Dependencies" section for the full list. MSRV
  is 1.86.
- **jellyfish vs rapidfuzz crate choice**: keep both. An earlier revision tried to
  collapse to jellyfish alone, but benchmark research showed rapidfuzz's bit-parallel
  distance algorithms (Myers/Hyyrö/Mbleven) run 3–10× faster than jellyfish's DP
  implementation for our typical 5–50 char name inputs. Since the whole port's speed
  case is load-bearing, we take both: jellyfish for metaphone/soundex (rapidfuzz
  doesn't have those) and rapidfuzz for distance. See "Why jellyfish AND rapidfuzz"
  in Key Design Decisions for full rationale.
