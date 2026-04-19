---
description: Rust-only ownership of text wordlist and symbol resources (stopwords, nullwords, nullplaces, ordinals, name prefixes, org/person symbols) — JSON shape, PyO3 accessors, Python consumer wiring
date: 2026-04-19
tags: [rigour, rust, resources, stopwords, ordinals, symbols, genscripts]
---

# Rust-only resources: stopwords, ordinals, name prefixes, symbols

## Context

The rust-core port is moving text resources from generated Python
(`rigour/data/**/*.py`) to JSON files under `rust/data/` that the Rust
crate pulls in via `include_str!` + `serde_json` (see the existing
`rust/data/org_types.json` → `rust/src/names/org_types.rs` path, and
the Tier-3 contract in `genscripts/util.py:45` `write_json`).

Four resources are in scope:

- `resources/text/stopwords.yml` — `STOPWORDS`, `NULLWORDS`,
  `NULLPLACES` (three flat string lists used by
  `rigour/text/stopwords.py:31,59,88`).
- `resources/names/stopwords.yml` — `PERSON_NAME_PREFIXES`,
  `ORG_NAME_PREFIXES`, `OBJ_NAME_PREFIXES`, `NAME_SPLIT_PHRASES`,
  `GENERIC_PERSON_NAMES` (five flat string lists used by
  `rigour/names/{prefix,split_phrases,check}.py`). Despite the
  filename, these are **not** stopwords in the usual sense — they are
  name-part classifiers.
- `resources/text/ordinals.yml` — `ordinals: { <int>: [form, ...] }`
  used by `rigour/names/tagging.py:75` (symbol tagger) and
  `rigour/addresses/normalize.py:104` (address expansion).
- `resources/names/symbols.yml` — five nested mappings
  (`org_symbols`, `org_domains`, `person_symbols`, `person_nick`,
  `person_name_parts`), each `dict[str, list[str]]` keyed by a
  canonical/representative form (e.g. `co`, `jr`, `bob`) with a list
  of aliases/variants. Consumed by `rigour/names/tagging.py:92,105,202`
  to build the org- and person-name symbol automatons. Structurally
  different from the other three (**nested dict**, not flat list),
  so gets its own section below.

The goal of this plan: make **Rust the single source of truth** for
the raw wordlists, expose tiny accessor functions through PyO3 that
return the raw strings, and let the existing Python call sites
continue to normalize and build their `@cache`d sets exactly as they
do today. Python-side behaviour is unchanged; only the data's home
moves. This retires the per-resource Python codegen entirely for
these three files.

## Design

### 1. JSON shapes — mirror `resources/` layout in `rust/data/`

One YAML file maps to one JSON file. Mirror the directory tree so the
two `stopwords.yml` files don't collide:

- `rust/data/text/stopwords.json`
- `rust/data/text/ordinals.json`
- `rust/data/names/stopwords.json`
- `rust/data/names/symbols.json`

Rust consumer modules land at `rust/src/text/stopwords.rs`,
`rust/src/text/ordinals.rs`, `rust/src/names/stopwords.rs`,
`rust/src/names/symbols.rs`. Module path + directory prefix
disambiguates at three layers (filesystem, Rust module, Python
`rigour._core.*` accessor).

### 2. Multi-section YAML → JSON object with typed fields

Keep the section structure; lowercase snake_case the field names:

`rust/data/text/stopwords.json`:

```json
{
  "stopwords":  ["&", "a", "al", ...],
  "nullwords":  ["---", "N/A", ...],
  "nullplaces": ["abroad", "antilles", ...]
}
```

Same for `rust/data/names/stopwords.json` with fields
`person_name_prefixes`, `org_name_prefixes`, `obj_name_prefixes`,
`name_split_phrases`, `generic_person_names`. Sorted, de-duplicated,
`norm_string`-ed — same invariants the current `generate_text.py` /
`generate_names.py` already enforce.

### 3. Ordinals: array of typed records

JSON has no integer keys. Use an array of `{number, forms}` — matches
the `org_types.json` precedent, needs no string-to-int parse, is
serde-friendly:

```json
[
  {"number": 0, "forms": ["#0", "(0)", "0th", "Nil", ...]},
  {"number": 1, "forms": ["#1", "(1)", "1-e", "1-й", ..., "First", ...]}
]
```

```rust
#[derive(Deserialize)]
struct OrdinalSpec {
    number: u32,
    forms: Vec<String>,
}
```

Outer array sorted by `number`, each inner `forms` sorted — same
ordering hygiene as `org_types.json`.

### 4. Symbols: nested dict → JSON object of objects

`resources/names/symbols.yml` has five top-level sections, each a
`dict[str, list[str]]`. The JSON mirrors this 1:1 — one file with
five keys, each a `{group_key: [aliases...]}` object:

```json
{
  "org_symbols": {
    "co":   ["company", "corporation", "corp", ...],
    "org":  ["organization", "organisation", ...],
    "corp": ["corporation", "corp", ...]
  },
  "org_domains":       {...},
  "person_symbols":    {"jr": ["Jr", "Junior", ...], "sr": [...]},
  "person_nick":       {"bob": ["Bob", "Robert"], ...},
  "person_name_parts": {"khuylo": [...], "qdfi": [...]}
}
```

Group keys are `UPPER`-cased at Python consumption time today
(`rigour/names/tagging.py:99` does `key.upper()` when building
`Symbol(Symbol.Category.SYMBOL, key.upper())`). Keep them lowercase
in the JSON — the Python consumer still `.upper()`s them, unchanged
from today. No effort to preserve YAML comments or insertion order;
each inner list is sorted and de-duplicated by the generator, same
invariants as the other files.

Rust-side struct:

```rust
#[derive(Deserialize)]
struct NameSymbols {
    org_symbols:       HashMap<String, Vec<String>>,
    org_domains:       HashMap<String, Vec<String>>,
    person_symbols:    HashMap<String, Vec<String>>,
    person_nick:       HashMap<String, Vec<String>>,
    person_name_parts: HashMap<String, Vec<String>>,
}
```

PyO3 converts `HashMap<String, Vec<String>>` to `dict[str, list[str]]`
natively, matching the shape Python consumers already iterate with
`for key, values in ORG_SYMBOLS.items():`.

### 5. Rust owns the data — Python reads through `_core` accessors

No more Python codegen for these resources. `rigour/data/text/stopwords.py`,
`rigour/data/text/ordinals.py`, and `rigour/data/names/data.py` are
**retired in full** — every section that file currently holds has a
new JSON source (the five flat wordlists from `names/stopwords.yml`
plus the five nested dicts from `names/symbols.yml`).

Rust crate exposes accessor functions that return raw lists/tuples to
Python:

```rust
// rust/src/text/stopwords.rs (sketch)
use serde::Deserialize;
use std::sync::LazyLock;

#[derive(Deserialize)]
struct TextStopwords {
    stopwords:  Vec<String>,
    nullwords:  Vec<String>,
    nullplaces: Vec<String>,
}

const JSON: &str = include_str!("../../data/text/stopwords.json");
static DATA: LazyLock<TextStopwords> =
    LazyLock::new(|| serde_json::from_str(JSON).expect("text/stopwords.json parses"));

#[pyfunction] pub fn stopwords()  -> Vec<String> { DATA.stopwords.clone() }
#[pyfunction] pub fn nullwords()  -> Vec<String> { DATA.nullwords.clone() }
#[pyfunction] pub fn nullplaces() -> Vec<String> { DATA.nullplaces.clone() }
```

Analogous `#[pyfunction]`s for the names file:
- `person_name_prefixes()`, `org_name_prefixes()`,
  `obj_name_prefixes()`, `name_split_phrases()`,
  `generic_person_names()`.

For ordinals:

```rust
#[pyfunction]
pub fn ordinals() -> Vec<(u32, Vec<String>)> {
    DATA.iter().map(|o| (o.number, o.forms.clone())).collect()
}
```

For symbols — five accessors, each returning the inner dict as-is:

```rust
#[pyfunction] pub fn org_symbols()       -> HashMap<String, Vec<String>> { DATA.org_symbols.clone() }
#[pyfunction] pub fn org_domains()       -> HashMap<String, Vec<String>> { DATA.org_domains.clone() }
#[pyfunction] pub fn person_symbols()    -> HashMap<String, Vec<String>> { DATA.person_symbols.clone() }
#[pyfunction] pub fn person_nick()       -> HashMap<String, Vec<String>> { DATA.person_nick.clone() }
#[pyfunction] pub fn person_name_parts() -> HashMap<String, Vec<String>> { DATA.person_name_parts.clone() }
```

Python-side consumers barely change:

```python
# rigour/text/stopwords.py  (today)
from rigour.data.text.stopwords import STOPWORDS
# becomes
from rigour._core import stopwords as _stopwords_raw
STOPWORDS = tuple(_stopwords_raw())
```

…and the existing `@cache`d `_load_stopwords(normalizer)` that
applies the caller's normalizer and builds a `set[str]` keeps working
unchanged. Same for `_load_nullwords`, `_load_nullplaces`,
`_load_generic_person_names`, the prefix and split-phrase regex
builders in `rigour/names/prefix.py` and `rigour/names/split_phrases.py`,
the ordinals loop at `rigour/names/tagging.py:75-86` and
`rigour/addresses/normalize.py:104-107`, and the symbol/domain/person
tagger loops at `rigour/names/tagging.py:98-110,202-…`. Each call
site just swaps `from rigour.data.names.data import ORG_SYMBOLS` for
`from rigour._core import org_symbols; ORG_SYMBOLS = org_symbols()`
(or an inline call on first use).

**FFI cost**: one call per resource at module-import time to
materialise a `list[str]` or `dict[str, list[str]]`. Zero per-token
FFI cost — normalization and set-membership checks stay in Python,
same as today. No regression on the matching hot path. `symbols.yml`
is the largest single resource (~3800 YAML lines, mostly Unicode
alias strings); one clone at import time is noisier than the flat
wordlists but still well under a millisecond.

**Data embedding**: `include_str!` bakes the JSON into the Rust
binary, so wheels are self-contained. Aligns with the "Data
embedding: compiled into the Rust binary" decision in the rust-core
project notes.

### 6. Clone vs. zero-copy — pick clone, note the alternative

`#[pyfunction] fn stopwords() -> Vec<String> { DATA.stopwords.clone() }`
allocates once at import time. The flat lists are small (tens to low
hundreds of entries, total ~5 KB across all three files); symbols is
larger but still bounded. A zero-copy path using `&'static [String]`
+ PyO3's `Vec<&str>` marshalling is possible but adds lifetime
plumbing for a one-shot import-time call. Not worth it; clone.

### 7. `.pyi` surface

Add stubs in `rigour/_core.pyi` for each new `#[pyfunction]`:

```python
def stopwords() -> list[str]: ...
def nullwords() -> list[str]: ...
def nullplaces() -> list[str]: ...
def person_name_prefixes() -> list[str]: ...
def org_name_prefixes() -> list[str]: ...
def obj_name_prefixes() -> list[str]: ...
def name_split_phrases() -> list[str]: ...
def generic_person_names() -> list[str]: ...
def ordinals() -> list[tuple[int, list[str]]]: ...
def org_symbols() -> dict[str, list[str]]: ...
def org_domains() -> dict[str, list[str]]: ...
def person_symbols() -> dict[str, list[str]]: ...
def person_nick() -> dict[str, list[str]]: ...
def person_name_parts() -> dict[str, list[str]]: ...
```

## Files to touch

### Generate scripts
- `genscripts/generate_text.py` — **delete** `generate_ordinals` and
  `generate_stopwords`; replace with two `write_json` calls that emit
  `rust/data/text/ordinals.json` (array of `{number, forms}`) and
  `rust/data/text/stopwords.json` (object of three arrays).
- `genscripts/generate_names.py` — rewrite `generate_data_file` as
  two `write_json` calls: one for the five flat wordlists
  (`rust/data/names/stopwords.json`) and one for the five nested
  symbol dicts (`rust/data/names/symbols.json`). Drop the Python
  codegen branch entirely. `generate_org_type_file` stays as-is (it
  already emits `rust/data/org_types.json` and is not in scope here).
- `genscripts/util.py` — ensure `write_json` creates parent dirs
  (`file_path.parent.mkdir(parents=True, exist_ok=True)` prepended to
  `write_json`), so `rust/data/text/` and `rust/data/names/` appear
  on demand.

### Rust crate
- `rust/src/text/mod.rs`, `rust/src/text/stopwords.rs` (new),
  `rust/src/text/ordinals.rs` (new).
- `rust/src/names/mod.rs`, `rust/src/names/stopwords.rs` (new),
  `rust/src/names/symbols.rs` (new).
- `rust/src/lib.rs` — register the fourteen new `#[pyfunction]`s on
  the `PyModule` (nine wordlist/ordinal accessors + five symbol
  accessors).

### Python
- `rigour/_core.pyi` — add stubs.
- `rigour/text/stopwords.py` — replace
  `from rigour.data.text.stopwords import STOPWORDS` (and similar)
  with `from rigour._core import stopwords as _stopwords_raw`; rebuild
  the module-level `STOPWORDS` tuple in place so nothing downstream of
  `_load_stopwords` changes.
- `rigour/names/prefix.py`, `rigour/names/split_phrases.py`,
  `rigour/names/check.py` — same substitution for the flat wordlists.
- `rigour/names/tagging.py:75-86,92,105,202` — pull `ORDINALS`,
  `ORG_SYMBOLS`, `ORG_DOMAINS`, `PERSON_SYMBOLS`, `PERSON_NAME_PARTS`,
  `PERSON_NICK` from the corresponding `rigour._core.*()` accessors
  instead of importing from `rigour.data.*`. Drop the
  `unload_module("rigour.data.names.data")` / `unload_module(
  "rigour.data.text.ordinals")` calls — there's no Python module to
  unload; the Rust side owns the data. Memory is already held by the
  `LazyLock<...>` in Rust and is not reclaimable.
- `rigour/addresses/normalize.py:104-107,151` — same substitution for
  ordinals; drop the `unload_module("rigour.data.text.ordinals")`
  call.

### Deletions
- `rigour/data/text/stopwords.py` — delete; the file is no longer
  generated.
- `rigour/data/text/ordinals.py` — delete; same.
- `rigour/data/names/data.py` — **delete in full**. Every section
  (`PERSON_NAME_PREFIXES`, `ORG_NAME_PREFIXES`, `OBJ_NAME_PREFIXES`,
  `NAME_SPLIT_PHRASES`, `GENERIC_PERSON_NAMES`, `ORG_SYMBOLS`,
  `ORG_DOMAINS`, `PERSON_SYMBOLS`, `PERSON_NAME_PARTS`, `PERSON_NICK`)
  has a JSON equivalent now.

### `unload_module` pattern
Today both tagging.py and addresses/normalize.py call
`unload_module()` on the Python data modules after building their
lookup structures, to free the module-level tuples/dicts. After the
port, the LazyLock-held Rust data is process-lived and not
reclaimable; drop the calls rather than leaving dead references. The
total data footprint is small (symbols ~300 KB compressed JSON at
most, flat lists ~5 KB) so this is not a regression worth engineering
around.

### `resources/names/stopwords.yml` rename (optional, out of scope)
The YAML file name is misleading — contents are prefixes + split
phrases + generic full names, not stopwords. A rename to
`resources/names/name_parts.yml` or a split into per-section files
would clarify. Punt to a follow-up; this plan keeps the filename
as-is so the diff is scoped.

## Verification

- `make generate` produces four new JSON files with stable, sorted
  output, and no longer writes `rigour/data/text/stopwords.py`,
  `rigour/data/text/ordinals.py`, or `rigour/data/names/data.py`.
- `python -c "from rigour._core import stopwords, ordinals, org_symbols; assert len(stopwords()) > 100; assert any(n == 1 for n, _ in ordinals()); assert 'co' in org_symbols()"`.
- `pytest --cov rigour tests/text/test_stopwords.py tests/names/test_check.py tests/names/test_prefix.py tests/names/test_tagging.py tests/addresses/` — all pass unchanged; the Python API didn't move.
- `mypy --strict rigour` on the edited modules.
- Parity check during the port: for each retired Python constant,
  assert that the Rust accessor returns the same set of entries
  (`set(_core.stopwords()) == set(OLD_STOPWORDS)`; for the nested
  symbol dicts, compare keys and each value as a `frozenset`) before
  removing the `.py` file. Run once locally, don't keep in CI.
