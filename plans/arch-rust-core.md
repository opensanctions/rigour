---
description: Architecture of rigour's Rust core — module layout, build system, FFI conventions, data embedding, and the rules that govern what lives in Rust vs. Python.
date: 2026-04-26
tags: [rigour, rust, architecture, pyo3, icu4x, maturin]
---

# rigour Rust core: architecture

## Why a Rust core at all

The hot path in the OpenSanctions matching stack is name analysis,
called per-entity at scale. The pre-port Python implementation
crossed the PyO3 / PyICU / `ahocorasick-rs` boundaries at fine
granularity — per character, per token, per AC match — and the
boundary cost dominated the actual work.

A January-2026 attempt on the `fafo-rust` branch tried to fix this
by binding ICU4C through `rust_icu_utrans`. Result: still slower
than Python+PyICU, because the Python→Rust→ICU4C double hop didn't
beat Python→ICU4C directly. **Lesson: port larger chunks.** The
hot loop has to run entirely in Rust, crossing the Python boundary
only at coarse entry/exit points.

That principle drives almost every architectural decision below.

## What the Rust core contains

Live module layout under `rust/src/`:

| Module | Responsibility |
|---|---|
| `text/normalize.rs` | `Normalize` bitflags + `Cleanup` enum + composed `normalize()` pipeline |
| `text/tokenize.rs` | Unicode-category-aware `tokenize_name` |
| `text/translit.rs` | `should_ascii` + `maybe_ascii` over the 6 LATINIZE_SCRIPTS |
| `text/scripts.rs` | `codepoint_script`, `text_scripts`, `common_scripts` |
| `text/phonetics.rs` | metaphone / soundex via the `rphonetic` crate |
| `text/numbers.rs` | `string_number` — Unicode-aware numeric parser |
| `text/distance.rs`, `ordinals.rs`, `stopwords.rs` | data accessors and primitives |
| `names/name.rs`, `part.rs`, `symbol.rs`, `tag.rs` | the `Name` / `NamePart` / `Span` / `Symbol` / `NamePartTag` / `NameTypeTag` pyclasses |
| `names/analyze.rs` | the single-FFI `analyze_names` pipeline |
| `names/tagger.rs`, `symbols.rs`, `org_types.rs`, `prefix.rs` | tagger, org-type replacer, prefix stripper |
| `names/matcher.rs` | `Needles<T>` substrate (Aho-Corasick + Python-style `\b` post-filter) |
| `names/pick.rs` | `pick_name` / `pick_case` / `reduce_names` |
| `names/pairing.rs`, `alignment.rs` | symbol pairing + person-name alignment helpers |
| `territories.rs` | territory data accessor |
| `lib.rs` | PyO3 bindings, `_core` pymodule registration |

The full name-analysis architecture and the `text/normalize` /
`text/translit` design live in their own arch docs:

- `plans/arch-name-pipeline.md` — Symbol / Name / NamePart object
  graph, `analyze_names`, `pick_name`, `pair_symbols`, the
  cross-stack adapter pattern.
- `plans/arch-text-normalisation.md` — `Normalize` flag set,
  `tokenize_name`, `maybe_ascii`, `common_scripts`, normality's
  status as an explicit non-goal.

This document is the umbrella: cross-cutting conventions that
apply across both.

## Architectural premises

**Only rigour contains Rust.** FTM, nomenklatura, yente, zavod,
and OpenSanctions stay pure Python. They reach Rust through
rigour's normal Python API. The PyO3 bindings are an internal
implementation detail of rigour, not a public surface.

**Existing Python imports keep working.** `from rigour.names
import Name, tokenize_name` and similar continue with their
pre-port signatures. Where a function moved from Python to Rust,
the Python module shrinks to a thin wrapper around the
`rigour._core` export. Migration of downstream callers to coarser
entry points (e.g. `analyze_names`) happens repo-by-repo without
breaking the fine-grained API.

**Eagerly compute derived properties on pyclasses.** `NamePart`'s
`form`, `ascii`, `comparable`, `metaphone`, `integer`, `latinize`,
`numeric` all compute at construction and cache as `Py<PyString>`
(or scalar) fields. Per-attribute access from Python is then an
INCREF, not a fresh allocation across the FFI boundary. The only
mutable derived property is `tag` — the tagging pipeline writes
it after construction, but no other cached property depends on
`tag`, so mutation doesn't invalidate anything.

**LRU caches at the Python boundary, never inside Rust.** The
principle is "cache at the boundary to skip the FFI." Rust calls
that are dramatically faster than the Python LRU lookup itself
(transliteration, tokenisation) get the cache dropped in their
Python wrapper. Rust calls comparable to or slower than the lookup
(metaphone, soundex hitting heavy-repetition workloads) keep
`@lru_cache` in their wrapper. Distance-style functions are
case-by-case. There are two narrow exceptions inside Rust where a
thread-local cap-N HashMap absorbs costly internal recursion (see
`rust/src/text/translit.rs` for `maybe_ascii`'s; the older
`ascii_text` had one too) — these exist because Rust-internal
callers don't go through the Python wrapper and would otherwise
pay the full cost on every nested call.

## Build system

**maturin replaces hatchling.** The Rust crate lives under
`rust/`; maturin compiles it to `rigour/_core.so` (Linux/macOS) or
the `.pyd` equivalent on Windows. `pyproject.toml` wires it; the
`python` Cargo feature gates the PyO3 bindings so plain
`cargo test` and `cargo build` work without a Python runtime
installed.

`rigour/py.typed` is required for downstream `mypy --strict` to
pick up the `.pyi` stubs. The stub file `rigour/_core.pyi`
declares every PyO3 export by hand — losing an entry there
silently turns into an `attr-defined` error downstream.

CI wheel matrix uses `PyO3/maturin-action@v1`: manylinux +
musllinux on x86_64 and aarch64, macOS x86_64 and arm64, Windows
x64. Python 3.10–3.13. Publish-on-tag via
`pypa/gh-action-pypi-publish`. Live config:
`.github/workflows/build.yml`.

`make develop-debug` is the fast Rust-iteration path
(`maturin develop` without `--release`); `make develop` builds
release-mode for benchmark / production use. ICU4X's trie-heavy
transliteration paths are dramatically slower in debug, so any
performance characterisation needs release builds.

## ICU4X over ICU4C

The pivot from ICU4C (via `rust_icu_utrans`) to ICU4X (the `icu`
crate, pure Rust) was decisive for two reasons:

1. **Windows support became free.** No system ICU, no link-time
   ICU bundling, no manylinux/musllinux library-bundling
   gymnastics. One row in the CI matrix; no source is
   Windows-aware.
2. **Build-time data embedding replaces runtime file lookup.**
   `compiled_data` + `unstable` features bake ~3 MB of CLDR data
   into the binary. No `__file__` resolution, no
   `importlib.resources`, no path-not-found surprises in odd
   deployment environments.

ICU4X 2.x ships per-script transliterators (Cyrillic, Greek,
Armenian, Georgian, Hangul, Arabic, Han, Hebrew, Hiragana,
Katakana, plus several Indic and Ethiopic scripts) but does NOT
ship `Any-Latin` — the compound transliterator PyICU uses. We do
per-script dispatch instead. The trade-off and the resulting
script coverage live in `arch-text-normalisation.md`.

ICU4X's `Transliterator` is `!Send + !Sync`, so the cache uses
`thread_local!` with `RefCell` rather than `LazyLock`. Under the
Python GIL this is effectively a process-lifetime singleton —
free-threaded Python (PEP 703) would change that, see the open
questions below.

## Data embedding: three tiers

All resource data compiles into the Rust binary. No runtime file
I/O. The YAML / text files in `resources/` are the canonical
human-edited source of truth; `genscripts/` (Python) emits
per-consumer artifacts under `rust/data/` and
`rust/src/generated/`.

**Tier 1 — compressed pattern list, rebuild on first use.** Used
for the person-names corpus (~150k Aho-Corasick patterns,
compressed to ~3 MB on disk). Plain UTF-8 committed at
`rust/data/names/person_names.txt` for diffability;
`rust/build.rs` zstd-compresses into `OUT_DIR`; the loader
decodes via `include_bytes!` on first access. Tagger builds the
automaton inside a `LazyLock<AhoCorasick>` on first access. The
one-time decompress + AC build cost is paid on first tagger use
per process.

`aho-corasick` v1 exposes no serde or raw-byte serialisation,
so the build is from-source. If startup cost ever matters,
`daachorse` (double-array AC with explicit serialisation) is the
escape hatch.

**Tier 2 — sorted-slice `.rs` literals.** Used for Unicode script
ranges, Latin/Latinizable sets, and similar small static lookups.
`genscripts/` emits `&'static [(K, V)]` slice literals into
`rust/src/generated/`. Lookup is `slice::binary_search_by_key` —
competitive with `phf` at our sizes and vastly simpler to
generate.

**Tier 3 — JSON / JSONL inside `LazyLock`.** Used for org types,
territories, org/person symbol dictionaries — a few hundred to a
few thousand structured records with nested optional fields.
Parse cost is sub-millisecond on first access; JSON is
human-inspectable when a regeneration looks wrong. `serde` /
`serde_json` are the only dependencies.

### Formats explicitly rejected

- **bincode / postcard / rkyv across the board** — diff-hostile,
  zero-copy gains are irrelevant after init.
- **MessagePack** — same trade-off, no benefit at our sizes.
- **YAML at runtime (`serde_yaml`)** — unnecessary dep, slower
  than JSON.
- **Embedding generated Python** — dead end.

### Genscripts stays Python

The generators use the broader Python ecosystem (Wikidata client,
`unidecode`, existing rigour utilities), run rarely, and would
double in size to rewrite. The clean split is **Python generates,
Rust consumes.** `make rust-data` regenerates everything under
`rust/data/` + `rust/src/generated/`; CI runs it and `git diff`s
against the committed artifacts as the contract.

### Source-of-truth boundary

Migration of resource data to Rust is driven by what the Rust
pipeline needs, not by a goal of unifying the data layer.
Datasets that only Python ever reads stay Python-consumed.

Live state of `rigour/data/` today:

```
rigour/data/
├── __init__.py                   # DATA_PATH, iter_jsonl_text — stays
├── addresses/
│   ├── __init__.py
│   ├── data.py                   # FORMS — pending Rust port
│   └── formats.yml
└── langs/
    ├── __init__.py
    └── iso639.py                 # ISO tables — low priority
```

Everything else under `rigour/data/` has retired: `names/`,
`text/`, and `territories/` are gone. The remaining two are
covered in *Open questions* below.

## Convention: word boundaries on Aho-Corasick

The `regex` crate doesn't support lookahead / lookbehind. For the
literal-alias matching in org-types and the tagger, we implement
Python-style `(?<!\w)X(?!\w)` as a post-filter on Aho-Corasick
matches in `rust/src/names/matcher.rs::Needles<T>`. The byte-level
boundary check decodes a single codepoint on each side of the
match span and consults `is_alphanumeric` (Unicode-aware via the
`char` API). CJK characters are `\w` in `re.U`, so `\b` doesn't
fire between them — this matches existing Python behaviour
exactly.

The address replacer (still Python regex) uses the same shape
explicitly with negative lookarounds. When the address pipeline
ports to Rust the regex collapses into a `Needles<String>` of the
same kind.

## Crate dependencies

Live config: `rust/Cargo.toml`. Current set as of this writing:

- `pyo3` — `extension-module` + `generate-import-lib` (Windows
  link stub).
- `icu` 2 — `compiled_data` + `unstable` for transliteration.
- `bitflags` — `Normalize` flag set.
- `rphonetic` — metaphone, soundex. Chosen over `jellyfish`
  because `jellyfish` is cdylib-only and conflicts with our pyo3
  link.
- `aho-corasick` v1 — multi-needle literal search backing
  `Needles<T>`.
- `rapidfuzz` 0.5 — Levenshtein for the Rust-internal
  `pick_name`. Not exposed via PyO3 — see the opcodes-gap open
  question below.
- `serde` / `serde_json` — Tier-3 loaders.
- `zstd` — person-names corpus compression at build time.

MSRV is whatever `icu` pins (currently 1.86). Bumping the icu
crate is the most common reason MSRV moves.

## Symbol IDs are always strings

Pre-port, `Symbol.id` was heterogeneous: `int` for numeric
categories (Wikidata QIDs, ordinals), `str` for everything else.
The Rust port stringifies all IDs at construction, simplifying
both the Rust struct and the PyO3 boundary. Wikidata QIDs keep
the `Q` prefix in their string form. Full design rationale —
including why `u32` + per-category tables was rejected — lives
in `arch-name-pipeline.md`.

## Open questions

These are tracked because each has a known-but-not-yet-pulled
trigger. They're not aspirations; they're decisions deferred
until specific evidence arrives.

### Distance / rapidfuzz opcodes gap

Python's `rapidfuzz` exposes `Levenshtein.opcodes(s1, s2)` for
alignment recovery; nomenklatura's `_opcodes` is `@lru_cache`d
over it. The Rust `rapidfuzz` 0.5 crate has no equivalent — it
exposes distance and similarity scores only.

Implication: a Rust-side distance port wouldn't let us drop the
Python `rapidfuzz` dep, because nomenklatura still needs opcodes.
And Python `rapidfuzz`'s C++ backend already runs the same
bit-parallel algorithms, so there's no speed regression from
keeping distance on the Python side.

Plan of record: keep Python `rapidfuzz` for distance + opcodes.
Three options if this changes:

- **(A)** Status quo. Simplest.
- **(B)** Rust-side distance + Python-side opcodes. Pointless —
  no net dep reduction.
- **(C)** Implement opcodes in Rust (port Hyyrö's bit-parallel
  alignment from `rapidfuzz-cpp`, or Wagner-Fischer with
  traceback). Real implementation effort, or upstream the API to
  the Rust `rapidfuzz` crate.

Don't half-port distance without re-reading this block.

### normality stays

`normality` provides broad-script transliteration via PyICU
(`ascii_text`, `latinize_text`) and a few utility helpers
(`category_replace`, `squash_spaces`, `WS`, `Categories`). All
options for replacing it now have a high maintenance or quality
cost — ICU4X doesn't ship Thai / Khmer / Lao / Sinhala / Tibetan
in `compiled_data`, the `anyascii` backend swap has unresolved
quality questions for CJK names, and the per-script-walks
performance gap on mixed-script inputs is real.

The non-goal sticks until ICU4X feature-parity with PyICU on the
script ranges we actually use, or until anyascii's quality on
real corpora is measured. See `arch-text-normalisation.md` for
the full backend landscape.

### Address-normalize Rust port

`rigour/addresses/normalize.py` still owns the Python regex-based
replacer (recently inlined off `rigour.text.dictionary`). The
mapping is large — FORMS + ordinals + ~250 territories with
multiple names each — and Aho-Corasick scales to thousands of
patterns better than regex alternation. The escape-hatch is
exposing `Needles<String>` as a generic Rust pyclass and routing
the address replacer through it. Same primitive could absorb any
future "alias-replace on a wordlist" callers.

The `@cache` decorator on `_address_replacer` already amortises
the build cost, so the runtime gain is bounded. Worth doing only
if profiling shows address normalisation hot in a production
workload, OR as a follow-up to a more general-purpose
`text::dictionary` Rust pyclass.

### ISO-639 Rust port

`rigour/data/langs/iso639.py` is pure ASCII tables (~few KB).
No performance or memory motivation to move it. Port only when
language handling otherwise gets Rust work — currently
unscheduled.

### Free-threaded Python (PEP 703)

`thread_local!` for the ICU4X transliterator cache assumes one
worker per Python thread, which the GIL guarantees today. Under
free-threaded builds (`python3.13t`+), each OS thread pays
transliterator init separately. Decision needed when we ship
free-threaded wheels: `abi3` only (no per-thread overhead change),
or add `cp313t` / `cp314t` to the matrix and accept the
thread-multiplied init cost. The transliterator init is the most
expensive thread-local cache; everything else uses `LazyLock`
which works fine across threads.

### Person-tagger startup cost

Zstd decode + AC construction on first tagger access takes some
time (rough ~100 ms order, depends on hardware). For server
processes that keep the tagger alive this is paid once and
forgotten. For short-lived CLI tools or test runs it's visible.
If it ever matters, `daachorse` exposes a serialisable
double-array AC with explicit byte-format serialisation — worth a
spike at that point.

### `analyze_names` API surface

Currently a kwargs function. An `#[pyclass] AnalyzeRequest`
shape would be more type-safe and extensible. Decided
case-by-case if/when new flags arrive.

### Resolved (recorded so they don't get re-litigated)

- **Build backend**: hatchling → maturin. Plain replacement.
- **`consolidate_names` return type**: `Vec<Name>`; semantics
  collapse-shorter-into-longer by `contains()`, not strict
  equality.
- **ICU4X data feature**: `compiled_data` + `unstable`. Trim
  becomes possible only if we move off ICU4X transliteration
  entirely.
- **Phonetics crate**: `rphonetic`, not `jellyfish` (cdylib
  conflict with our pyo3 link).
- **Genscripts language**: Python. Rust consumes; CI no-diff
  check is the contract.
- **Wheel size**: net-neutral to net-smaller than pre-port.
- **Symbol.id type**: always `String` in Rust, always `str` in
  Python. Heterogeneous int-or-str rejected in `arch-name-pipeline.md`.
