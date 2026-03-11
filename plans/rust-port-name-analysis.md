---
description: Port name analysis pipeline (org_types, tagging, entity_names loop) to Rust via rigour-core
date: 2026-03-11
tags: [rigour, nomenklatura, rust, performance, names, tagging, org-types]
---

# Rust Port: Name Analysis Pipeline

## Architectural Premises

**Only rigour will ever contain Rust.** FTM, nomenklatura, and all other libraries in the
stack remain pure Python. They access Rust functionality exclusively through rigour's normal
Python API — the PyO3 bindings are an internal implementation detail of rigour, invisible to
callers. No other library in the stack will have a `rigour-core` dependency, a `maturin`
build step, or any Rust toolchain requirement.

This means the `NameStructure` bridge object (see below) must live in rigour, not nomenklatura,
and the `analyze_names` function must be callable as plain Python with no knowledge of Rust.

**Optimise for both performance and memory.** Every layer of the port should consider both
axes. Python objects carry substantial overhead even with `__slots__`: a reference count,
type pointer, and per-slot storage means even a small object like `NamePart` costs hundreds
of bytes. Rust structs are dense value types — the same data fits in tens of bytes. For a
process that holds tens of thousands of tagged `Name` objects in memory (the nomenklatura
index), the aggregate memory saving is significant and reduces GC pressure on the Python side.

---

## Motivation

`entity_names` in `nomenklatura/matching/logic_v2/names/analysis.py` is the hottest function
in the matching stack. For every entity comparison, it is called once per entity (cached by
entity ID). The cache helps across `result` candidates for the same `query`, but cold calls—
at data load time or after cache eviction—are dominated by:

1. `prenormalize_name` + `tokenize_name` × N names (Python string ops)
2. `replace_org_types_compare` (regex Replacer, one pass per name)
3. `tag_org_name` / `tag_person_name` (Aho-Corasick automaton, Python overhead per match)
4. `Name` / `NamePart` object construction (many small Python allocations)

Porting this pipeline to Rust (as a `rigour-core` Rust crate with PyO3 bindings) would
eliminate GIL pressure, reduce allocation overhead, and allow true parallelism over batches.

---

## The FTM Boundary Problem

`entity_names` takes an `EntityProxy` (from `followthemoney`). That object cannot cross
into Rust because FTM is pure Python and `EntityProxy` is not serializable without schema
lookup. The solution is a thin Python extraction layer that pulls the data we actually need
out of the entity and passes it to Rust as flat lists of strings.

The entity contributes two categories of data:
1. **Name strings** — `name`, `alias`, `previousName`, `weakAlias`, `abbreviation` — each
   of which becomes a separate `Name` object
2. **Part-tag hints** — `firstName`, `lastName`, `middleName`, `fatherName`, `motherName`
   — used to tag tokens within each `Name` with `GIVEN`, `FAMILY`, etc.

Both are `List[str]`. Everything else stays in Python.

---

## The `NameStructure` Bridge Object

`NameStructure` lives in `rigour/names/structure.py` and holds everything needed to analyze
a name without any FTM dependency. Fields map directly to FTM property names, making the
nomenklatura-side construction trivial and the Rust-side field layout explicit.

```python
# rigour/names/structure.py
from dataclasses import dataclass, field
from typing import List
from rigour.names.tag import NameTypeTag

@dataclass
class NameStructure:
    type_tag: NameTypeTag
    is_query: bool = False
    # Full name strings — each becomes a separate Name object
    name: List[str] = field(default_factory=list)
    alias: List[str] = field(default_factory=list)
    previousName: List[str] = field(default_factory=list)
    weakAlias: List[str] = field(default_factory=list)
    abbreviation: List[str] = field(default_factory=list)
    # Name part hints — used to tag tokens within each Name
    firstName: List[str] = field(default_factory=list)
    middleName: List[str] = field(default_factory=list)
    lastName: List[str] = field(default_factory=list)
    fatherName: List[str] = field(default_factory=list)
    motherName: List[str] = field(default_factory=list)
```

`name`, `alias`, `previousName`, `weakAlias`, and `abbreviation` are the name strings to be
analyzed — each entry produces one `Name` object. The `firstName`/`lastName`/etc. fields
supply values for `Name.tag_text()`, tagging matching tokens with `GIVEN`, `FAMILY`,
`MIDDLE`, `PATRONYMIC`, `MATRONYMIC` respectively.

The nomenklatura side builds this from `EntityProxy` and calls `analyze_names`:

```python
# nomenklatura — no Rust, no rigour internals
def build_name_structure(type_tag, entity, prop=None, is_query=False) -> NameStructure:
    ns = NameStructure(type_tag=type_tag, is_query=is_query)
    if prop is not None:
        ns.name = entity.get(prop, quiet=True)
    else:
        ns.name = entity.get_type_values(registry.name, matchable=True)
        ns.alias = entity.get("alias", quiet=True)
        ns.previousName = entity.get("previousName", quiet=True)
        ns.weakAlias = entity.get("weakAlias", quiet=True)
        ns.abbreviation = entity.get("abbreviation", quiet=True)
    ns.firstName = entity.get("firstName", quiet=True)
    ns.middleName = entity.get("middleName", quiet=True)
    ns.lastName = entity.get("lastName", quiet=True)
    ns.fatherName = entity.get("fatherName", quiet=True)
    ns.motherName = entity.get("motherName", quiet=True)
    return ns
```

---

## Rustification Scope

### Layer 1 — Core string operations (rigour-core, low difficulty)

| Python file | Functions | Rust notes |
|---|---|---|
| `rigour/names/tokenize.py` | `prenormalize_name`, `tokenize_name` | Unicode casefold, hyphen→space, strip punct; use `unicode-normalization` crate |
| `rigour/names/prefix.py` | `remove_person_prefixes`, `remove_org_prefixes` | Regex prefix strip; prefix lists loaded from YAML at startup |

### Layer 2 — Org type replacement (rigour-core, medium difficulty)

| Python file | Functions | Rust notes |
|---|---|---|
| `rigour/names/org_types.py` | `replace_org_types_compare`, `remove_org_types`, `extract_org_types` | Port the `Replacer`; see regex notes below; handle `compare: ""` as an explicit removal path |

**Regex engine choice for `Replacer`:**

The Python `Replacer` builds a single compiled alternation `(?<!\w)(LLC|GmbH|...hundreds of terms...)\b(?!\w)` with `re.I | re.U`. Porting this to Rust has one hard constraint: **the `regex` crate does not support lookahead or lookbehind**. Options:

- **`\b` word boundaries** (`regex` crate, native): replace `(?<!\w)...(?!\w)` with `\b...\b`. Unicode `\b` in `regex` is semantically equivalent for the token types we match. This forces the PikeVM engine (instead of the faster lazy DFA) but remains linear-time. For multi-alternation patterns on short strings, benchmarks (rebar suite) show Rust `regex` is roughly **10–30× faster** than Python `re` on longer text; for the 10–100 char company names in this use case the realistic gain is **5–15×** per call, because Python's per-call overhead (GIL, object allocation) does not disappear but the regex itself is faster.
- **`fancy-regex` crate**: a hybrid that wraps `regex` for the literal body and falls back to a bounded backtracker for the lookaround assertions. Benchmarks show fancy-regex handles `(?<!\w)LITERAL(?!\w)` patterns nearly as fast as plain `regex` `\b` because the backtracker only activates at the zero-width boundary check. Preserves exact Python semantics including CJK lookbehind behaviour.
- **Aho-Corasick + post-filter** (same pattern as `Tagger`): build the alternation as an AC automaton, then post-filter matches against token boundaries. This is what `tagging.py` already does and is the fastest option, but is more code and changes the architecture of `Replacer`.

**Recommended approach:** use `\b` with the `regex` crate. It is the simplest port and
avoids the `fancy-regex` dependency. Unicode `\b` in the `regex` crate treats CJK characters
as word characters (they have Unicode `\w` category), so `\b有限公司\b` inside a spaceless
CJK string fails to match for the same reason as Python's `(?<!\w)有限公司(?!\w)` — the
known CJK limitation is preserved identically.

**On Python caches:** `@cache` on `_compare_replacer` only avoids *rebuilding the compiled
regex object* — it is equivalent to `LazyLock<Replacer>` in Rust and is trivially matched.
`@lru_cache(maxsize=1024)` on `replace_org_types_compare` caches the *results* of individual
calls (input string → output string). In Rust the per-call cost of a compiled regex on a
short string will be low enough that this result cache is likely unnecessary — the same
argument as for `entity_names` above. Remove both and benchmark.

**Expected gain:** 5–15× per-call speedup for the regex itself. But the bottleneck is more
likely `Name`/`NamePart` object construction and the `Tagger` (Aho-Corasick over the GeoNames
corpus). Profile before investing heavily in `Replacer` optimisation.

**Key edge cases to preserve (all now test-covered):**
- `compare: ""` — remove, don't substitute (5 YAML entries incl. `к.д.`, `s.p.`)
- Dotted forms preserved by `_normalize_compare` but stripped by `tokenize_name` — two separate lookup tables
- Multi-word compound forms with internal punctuation (e.g. `GmbH & Co. KG`)
- CJK: `(?<!\w)` uses Unicode `\w`, so CJK chars block lookbehind — match Python behaviour exactly, do not fix
- `generic=True` falls back to text-as-is when no generic field exists

### Layer 3 — Aho-Corasick tagger (rigour-core, high difficulty)

| Python file | Functions | Rust notes |
|---|---|---|
| `rigour/names/tagging.py` | `tag_org_name`, `tag_person_name`, `_get_org_tagger`, `_get_person_tagger` | Use `aho-corasick` crate (overlapping mode); port `word_boundary_matches` using the same `[\w.-]+` boundary regex |

**Key details:**
- The tagger indexes only `display` and `compare` forms (aliases excluded unless `compare is None`)
- The tagger's normalizer strips dots: `"Sp. z o.o."` → key `"sp z oo"`; the org_types Replacer keeps dots
- `word_boundary_matches` in Python uses `re.compile(r"(?<!\w)([\w\.-]+)(?!\w)")` to build a set of char-index boundaries; replicate in Rust
- Tagger is loaded once (`@cache`), equivalent to Rust `LazyLock` — no behavioural change

**Memory:** the tagger `mapping` in Python is a `Dict[str, Set[Symbol]]` — each entry is a
Python dict bucket (56 B) + str object (~50–100 B) + set object + Symbol objects. The
GeoNames-derived person tagger loads tens of thousands of entries. In Rust a
`HashMap<String, Vec<Symbol>>` with interned strings and packed `Symbol` enums will use
**3–5× less memory** for the same dataset, and the Aho-Corasick automaton itself (already
in Rust via `ahocorasick_rs`) is unaffected.

### Layer 4 — ICU transliteration in Rust (rigour-core, prerequisite for NamePart)

`NamePart.ascii` currently calls `normality.ascii_text`, which uses PyICU with the script:

```
Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Accents-Any;
[:Symbol:] Remove; [:Nonspacing Mark:] Remove; Latin-ASCII
```

**Design decision**: implement ICU transliteration entirely in Rust using `rust_icu_transliterator`.
The `rust_icu_sys` build artifacts already exist in `rigour-core/target`, confirming this path
has been started. The same ICU script string works verbatim in Rust:

```rust
use rust_icu_transliterator::UTransliterator;

static ASCII_TRANS: LazyLock<UTransliterator> = LazyLock::new(|| {
    UTransliterator::new(
        "Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Accents-Any; \
         [:Symbol:] Remove; [:Nonspacing Mark:] Remove; Latin-ASCII",
        None, sys::UTransDirection::UTRANS_FORWARD,
    ).expect("ICU ASCII transliterator")
});

pub fn ascii_text(s: &str) -> String { ASCII_TRANS.transliterate(s) }
pub fn latinize_text(s: &str) -> String { /* Any-Latin */ }
```

`latinize_text` (used by `normality.scripts.can_latinize` and `NamePart.latinize`) also maps
to `Transliterator.createInstance("Any-Latin")`. Once both are in rigour-core, rigour can
expose them from `rigour.text` and drop its own PyICU dependency — the first step of the
normality subsumption strategy described below.

### Layer 5 — Data structures (rigour-core, high difficulty)

The `Name`, `NamePart`, `Symbol`, `Span` objects need Rust representations exposed via PyO3.
They are currently Python objects with `__slots__`. PyO3 `#[pyclass]` structs can expose them
with equivalent properties.

| Object | Key fields | Python size (est.) | Rust size (est.) |
|---|---|---|---|
| `Symbol` | `category: Category`, `id: SymbolId` | ~200 B (2 Python objects) | ~24 B (enum tag + u8 + String/i64) |
| `NamePart` | `form`, `index`, `tag`, `latinize`, `numeric`, `_ascii`, `_hash` | ~400 B (7 slots + cached str) | ~64 B (String + u32 + flags + Option<String>) |
| `Span` | `symbol`, `parts`, `comparable` | ~300 B + parts refs | ~48 B + indices into Name.parts |
| `Name` | `original`, `form`, `tag`, `parts`, `spans` | ~1–5 KB for a typical 5-part name | ~200–400 B |

A nomenklatura index holding 100k entities × 2 names each = 200k `Name` objects.
Python: ~200–1000 MB. Rust: ~40–80 MB. **Memory reduction: 5–25×.**

`Span.parts` in Python holds references to the same `NamePart` objects stored in `Name.parts`.
In Rust, store indices (`Vec<usize>`) into `Name.parts` instead of duplicating pointers —
eliminates reference overhead entirely and keeps `Span` trivially copyable.

`_ascii` is computed lazily in Python and cached on the object. In Rust, compute it on first
access and store as `Option<String>` inside the struct — same semantics, no Python object overhead.

### Layer 6 — `analyze_names` loop (rigour-core, low difficulty once layers 1–5 done)

Once `NameStructure` is defined and the above layers are ported, the inner loop of
`entity_names` is straightforward Rust:

```rust
pub fn analyze_names(ns: NameStructure) -> Vec<Name> {
    let mut seen = HashSet::new();
    let mut names = Vec::new();
    let raw_names = [ns.name, ns.alias, ns.previous_name, ns.weak_alias, ns.abbreviation].concat();
    let part_hints = [
        (ns.first_name,  NamePartTag::GIVEN),
        (ns.middle_name, NamePartTag::MIDDLE),
        (ns.last_name,   NamePartTag::FAMILY),
        (ns.father_name, NamePartTag::PATRONYMIC),
        (ns.mother_name, NamePartTag::MATRONYMIC),
    ];
    for raw in raw_names {
        let form = match ns.type_tag {
            PER => prenormalize_name(&remove_person_prefixes(&raw)),
            ORG | ENT => {
                let f = replace_org_types_compare(&prenormalize_name(&raw), false);
                remove_org_prefixes(&f)
            }
            _ => prenormalize_name(&raw),
        };
        if !seen.insert(form.clone()) { continue; }
        let mut sname = Name::new(&raw, &form, ns.type_tag);
        for (values, tag) in &part_hints {
            for value in values {
                sname.tag_text(&prenormalize_name(value), *tag);
            }
        }
        match ns.type_tag {
            ORG | ENT => tag_org_name(&mut sname, &normalize_name),
            PER => tag_person_name(&mut sname, &normalize_name, ns.is_query),
            _ => {}
        }
        names.push(sname);
    }
    names
}
```

---

## What Stays Python (For Now)

| Component | Reason |
|---|---|
| `entity.get_type_values(...)` / `entity._properties` | FTM EntityProxy is Python-only |
| `match_name_symbolic` (pairing, scoring) | Large scope, depends on `rapidfuzz`; separate phase |
| `weighted_edit_similarity` / `distance.py` | Depends on `rapidfuzz` opcodes; port separately |
| `consolidate_names`, `align_person_name_order` | Medium complexity; port in a later pass |
| `load_person_names()` (GeoNames data) | Large data loading; can pass pre-loaded data over boundary |

---

## PyO3 Binding Strategy

The Python-facing API should remain identical to the current Python API:

```python
# Python side (thin wrapper in rigour)
from rigour._core import analyze_names as _analyze_names  # PyO3 extension

def analyze_names(ns: NameStructure) -> Set[Name]:
    return set(_analyze_names(ns))
```

The `Name` objects returned from Rust must be usable by `match_name_symbolic` in Python.
This means `Name`, `NamePart`, `Symbol`, and `Span` must be `#[pyclass]` types in rigour-core.

### Transition path (avoids big-bang rewrite)

The layers above are ordered by logical dependency; the implementation phases below are
ordered by what unblocks what. ICU (Layer 4) is Phase 1 because `NamePart.ascii` depends
on it and the data structures (Layer 5) depend on `NamePart`.

1. **Phase 1**: ICU transliteration in Rust (`ascii_text`, `latinize_text`). Expose via PyO3.
   Validate output matches normality/PyICU for all test vectors. This also unblocks the
   normality subsumption work (rigour can drop its PyICU dependency after this phase).
2. **Phase 2**: Port `tokenize_name` and `prenormalize_name`. Python tests already cover these.
3. **Phase 3**: Port `org_types.py` functions (`replace_org_types_compare`, `remove_org_types`,
   `extract_org_types`). Keep Python fallback behind a feature flag during transition.
4. **Phase 4**: Port data structures (`Symbol`, `NamePart`, `Span`, `Name`) to PyO3 structs,
   with `NamePart.ascii` computed via Rust ICU from Phase 1. Run both in CI and compare outputs.
5. **Phase 5**: Port `tag_org_name` / `tag_person_name` with Aho-Corasick.
6. **Phase 6**: Introduce `NameStructure` and port the `entity_names` loop. Drop
   `lru_cache` on `entity_names` and benchmark.

At each phase, all existing tests in `tests/names/` remain the benchmark.
No nomenklatura changes are required until Phase 6.

The **normality pure-Python migration** (porting `squash_spaces`, `stringify`, `slugify`,
etc. to `rigour.text`) is independent of the Rust port and can proceed in parallel at any
point after Phase 1.

---

## Resource Loading

The tagger needs access to:
- `resources/names/org_types.yml` → currently compiled to `rigour/data/names/org_types.py`
- `resources/territories/*.yml` → compiled to `resources/territories/territories.jsonl`
- `resources/names/names/*.gz` (GeoNames person names)

The compiled Python data files (`org_types.py`, `data.py`) cannot be read by Rust directly.
The `genscripts/` build step that produces them will need to also emit a Rust-embeddable
format (JSON or a binary format like `bincode`/`postcard`) as a parallel output.

Loading options:
- **Embed at compile time** (`include_bytes!` + deserialize at first use) — zero runtime I/O,
  recommended for org_types and territories which are small and fixed at build time
- **Load from Python at startup, pass as bytes** across the PyO3 boundary — simpler to
  implement initially, acceptable for the person name corpus which is large and may be
  configurable

Recommended: embed org_types and territories; load person names via a Python-supplied
initializer on first use.

---

## Files to Create / Modify

**rigour:**
- `rigour-core/Cargo.toml` — new: Rust crate with PyO3 + aho-corasick deps
- `rigour-core/src/lib.rs` — PyO3 module root
- `rigour-core/src/transliterate.rs` — ICU `ascii_text` / `latinize_text` via rust_icu_transliterator
- `rigour-core/src/tokenize.rs` — prenormalize, tokenize
- `rigour-core/src/prefix.rs` — prefix removal
- `rigour-core/src/org_types.rs` — Replacer + compare/display forms
- `rigour-core/src/tagger.rs` — Aho-Corasick tagger + word_boundary_matches
- `rigour-core/src/names.rs` — Name/NamePart/Symbol/Span structs
- `rigour-core/src/analysis.rs` — analyze_names loop
- `rigour/names/structure.py` — new: `NameStructure` dataclass
- `rigour/names/analysis.py` — new: `analyze_names` wrapper (calls rigour-core or pure Python)
- `pyproject.toml` — add maturin build backend

**nomenklatura:**
- `nomenklatura/matching/logic_v2/names/analysis.py` — refactor `entity_names` to call
  `build_name_structure` + `rigour.names.analyze_names` (no behavior change, just split)

---

## Verification

```bash
# rigour
pytest tests/names/ -v           # all existing + new tests must pass
mypy --strict rigour             # no new type errors
cargo test -p rigour-core        # Rust unit tests

# nomenklatura (after Phase 6 integration)
pytest tests/matching/ -v
```

---

## normality Subsumption Strategy

The dependency stack is: **normality → rigour → followthemoney → nomenklatura**.

rigour currently depends on normality. The goal is for rigour to implement normality's full
API natively (ICU in Rust, pure Python for the rest), drop normality as a dependency, and
then have FTM and nomenklatura — which already depend on rigour — switch their own normality
imports to `rigour.text`. normality itself does not change at any point.

### Migration order

1. **rigour** implements all normality functionality natively in `rigour.text.*`:
   - `ascii_text` / `latinize_text` → `rigour._core` (Rust ICU, Phase 1 of port)
   - `squash_spaces`, `category_replace`, `remove_unsafe_chars` → pure Python in `rigour.text.cleaning`
   - `stringify` → `rigour.text.stringify`
   - `slugify`, `slugify_text` → `rigour.text.slugify`
   - `safe_filename` → `rigour.mime.filename` (already exists, just replace internal import)
   - `predict_encoding`, `guess_encoding` → `rigour.text.encoding`
   - `WS`, `UNICODE_CATEGORIES` → `rigour.text.constants`
   - `Categories`, `is_text` → `rigour.text.types`

   Then rigour replaces all `from normality import X` with `from rigour.text import X`
   and drops normality from `pyproject.toml`. The `ascii_text`/`latinize_text` step is
   blocked on rigour-core Phase 1; everything else can be done now.

2. **followthemoney** switches its 9 normality call sites to `rigour.text`. FTM already
   depends on rigour, so no new dependency is introduced.

3. **nomenklatura** switches its normality call sites to `rigour.text`. Already depends on
   both rigour and FTM.

4. **normality** is unreferenced and can be dropped from the stack.

### What rigour.text already has vs. what needs adding

`rigour/text/` currently has `cleaning.py`, `stopwords.py`, `dictionary.py`, `scripts.py`,
`checksum.py`, `phonetics.py` — but most still import from normality internally. After the
migration these become fully self-contained. The public `rigour.text` module needs to export
a compatible subset of the normality API so `from rigour.text import squash_spaces` is a
drop-in replacement throughout the stack.

---

## Open Questions

1. **`Symbol.id` heterogeneity**: IDs are either `str` (e.g. `"LLC"`) or `int` (GeoNames numeric
   IDs). A Rust enum `SymbolId` handles this cleanly, but PyO3 needs to map it to Python `Any`.

2. **`lru_cache` on `entity_names`**: Once the pipeline runs in Rust the cache may be
   unnecessary — the cost of re-running `analyze_names` on a cache hit will likely be lower
   than the overhead of hashing the entity and managing the cache. Remove it in Phase 6 and
   benchmark; re-introduce only if profiling shows a regression.

3. **Thread safety**: The Aho-Corasick automaton in Python is protected by `resource_lock`.
   In Rust, `LazyLock<AhoCorasick>` is `Send + Sync` by default — no lock needed.

4. **FTM migration timing**: FTM already depends on rigour, so switching from normality to
   rigour.text is straightforward. The main question is release sequencing — rigour must
   publish a stable `rigour.text` API before FTM cuts a release that drops normality.
