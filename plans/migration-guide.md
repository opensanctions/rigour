---
description: Migration guide for downstream consumers (followthemoney, nomenklatura, yente, zavod) against the rigour Rust-core release. Lists the breaking changes on the `rigour-rust-core` branch and the concrete before/after for each callsite pattern.
date: 2026-04-20
tags: [rigour, migration, breaking-changes, nomenklatura, yente, followthemoney, zavod]
---

# Migration guide — rigour Rust-core

This release ports the bulk of rigour's name-analysis stack to Rust.
Most of the public Python API is unchanged; a handful of functions
lose callback parameters in favour of flag sets, and the
`Symbol.id` type becomes uniformly `str`. Downstream repos
(followthemoney, nomenklatura, yente, zavod, opensanctions) need a
small set of coordinated edits.

This doc is the canonical "what do I need to change?" reference,
split by breaking change and then by repo.

## Cheat-sheet

| Change | Affected API | Rough edit |
|---|---|---|
| **`Symbol.id` is always `str`** (was `int \| str`) | `Symbol`, every `Symbol(...)` constructor, every `symbol.id` read | Compare against strings, not ints (`"1001"` not `1001`). Wikidata QIDs now include the `Q` prefix (`"Q4925477"` not `4925477`). |
| **Tagger `normalizer=` callback → `normalize_flags=` bitflags** | `tag_org_name`, `tag_person_name`, `replace_org_types_compare`, `replace_org_types_display`, `remove_org_types`, `extract_org_types` | Pass `normalize_flags=Normalize.CASEFOLD` (typical production default) instead of `normalizer=prenormalize_name`. |
| **Tagger `cleanup=` parameter removed** | `tag_org_name`, `tag_person_name` | Delete the argument if passed; tagger uses `tokenize_name` for category handling. |
| **`any_initials` → `infer_initials`** | `tag_person_name` | Rename the kwarg. |
| **Retired: `rigour.data.names.*`, `rigour.data.types`** | `ORG_TYPES`, `ORG_SYMBOLS`, `OrgTypeSpec`, etc. | No replacement at the Python data-module layer; the Rust tagger reads this data internally. Consumers using these symbols directly were only seen in test fixtures — update tests to construct expected values differently. |
| **Retired: `rigour.names.load_person_names` / `load_person_names_mapping`** | Person-names corpus iteration | No Python accessor. The Rust tagger reads the corpus internally. If you had a Python consumer, file an issue — there are no known downstream uses. |
| **Retired: module-level tuple constants** | `NAME_SPLIT_PHRASES`, `PERSON_NAME_PREFIXES`, `ORG_NAME_PREFIXES`, `OBJ_NAME_PREFIXES` in `rigour.names.{prefix,split_phrases}` | No replacement; internal refactor. External code shouldn't have imported these. |

## Per-change detail

### 1. `Symbol.id` is always `str`

Pre-port, `Symbol.id` was heterogeneous: `str` for YAML-keyed
symbols (`"LLC"`, `"FINANCE"`, `"INDUSTRY"`), `int` for numeric
categories (NUMERIC, some NAME). Now it's always `str`, with
integer-source IDs stringified at construction.

**Wikidata QIDs keep the `Q` prefix.** Pre-port code that parsed
QID numbers out of `Symbol.id` (`int(symbol.id)`) needs to compare
the full string (`"Q4925477"`). This is the only transformation
that's not purely mechanical.

```python
# Before
symbol = Symbol(Symbol.Category.NAME, 1001)
if symbol.id == 1001: ...
numeric = Symbol(Symbol.Category.NUMERIC, 5)
if numeric.id == 5: ...

# After
symbol = Symbol(Symbol.Category.NAME, "1001")   # or pass int; constructor stringifies
if symbol.id == "1001": ...
numeric = Symbol(Symbol.Category.NUMERIC, 5)    # int constructor still accepted
if numeric.id == "5": ...
```

The `Symbol.__init__` signature accepts `str | int` and
stringifies ints, so construction stays convenient. Reads
(`symbol.id`) always return `str`.

### 2. Tagger `normalizer=` → `normalize_flags=`

The tagger and `replace_org_types_*` functions used to accept a
`normalizer: Callable[[Optional[str]], Optional[str]]` that they
applied to their internal reference data at build time. The
parameter now accepts `Normalize` bitflags instead (full rationale
in `plans/rust-normalizer.md`).

The default `normalize_flags` value matches what nomenklatura /
yente / FTM already pass in practice — `Normalize.CASEFOLD` — so
dropping the argument entirely (letting it default) is usually the
right call.

```python
# Before
from rigour.names import replace_org_types_compare
from rigour.names.tokenize import prenormalize_name
form = replace_org_types_compare(form, normalizer=prenormalize_name)

# After
from rigour.names import replace_org_types_compare
form = replace_org_types_compare(form)       # default: normalize_flags=Normalize.CASEFOLD
```

```python
# Before
from rigour.names import tag_person_name
from rigour.names.tokenize import normalize_name
tag_person_name(name, normalize_name, any_initials=is_query)

# After
from rigour.names import tag_person_name
tag_person_name(name, infer_initials=is_query)  # default: normalize_flags=CASEFOLD|SQUASH_SPACES
```

If you need a non-default flag set:

```python
from rigour.text.normalize import Normalize
replace_org_types_compare(form, normalize_flags=Normalize.CASEFOLD | Normalize.SQUASH_SPACES)
```

### 3. Tagger `cleanup=` parameter removed

The tagger uses `tokenize_name` internally for Unicode-category
handling, which subsumes the role of `Cleanup::Strong`. The
parameter is gone end-to-end from `tag_org_name` /
`tag_person_name` and from the underlying PyO3 `tag_org_matches` /
`tag_person_matches`. Just drop any `cleanup=Cleanup.Strong`
kwarg.

`Cleanup` itself still exists and is still used by
`replace_org_types_*` / `remove_org_types` / `extract_org_types`;
only the tagger dropped it.

Side effect: the tagger now correctly preserves CJK `Lm` (e.g. `ー`
in `ウラジーミル`) and Brahmic/Indic `Mc` spacing marks in alias
matching — these used to be stripped alias-side but kept
haystack-side.

### 4. `any_initials` → `infer_initials`

Same concept, clearer name.

```python
# Before
tag_person_name(name, normalizer, any_initials=True)

# After
tag_person_name(name, infer_initials=True)
```

### 5. Retired modules

- `rigour.data.names.data` — held `ORG_SYMBOLS`, `ORG_DOMAINS`,
  `PERSON_SYMBOLS`, `PERSON_NICK`, `PERSON_NAME_PARTS`.
- `rigour.data.names.org_types` — held `ORG_TYPES`.
- `rigour.data.types` — held `OrgTypeSpec`.
- `rigour.names.person_names` — held `load_person_names` /
  `load_person_names_mapping`.
- `rigour.data.names.__init__` and `rigour.data.text.__init__`
  (empty packages).

All five are deleted. Their data is consumed by the Rust tagger
internally. No external rigour consumers were found (`grep` across
nomenklatura, yente, followthemoney, zavod, opensanctions came up
empty), so removal should be a no-op. If you had a private use,
the data still lives at `resources/names/*.yml` / `resources/names/
org_types.yml` at the top of the rigour repo.

### 6. Retired module-level tuple constants

`rigour.names.prefix` and `rigour.names.split_phrases` used to
expose `PERSON_NAME_PREFIXES`, `ORG_NAME_PREFIXES`,
`OBJ_NAME_PREFIXES`, `NAME_SPLIT_PHRASES` as `Tuple[str, ...]` at
module level, plus tuple-keyed `re_prefixes` / `re_split_phrases`
regex factories. Both sets are gone; the public `remove_*_prefixes`
and `contains_split_phrase` functions are unchanged.

## Per-repo punch list

Grep-verified as of this release. Exact line numbers will drift.

### followthemoney

- `followthemoney/compare.py:111` — `replace_org_types_compare(name)` already uses the new signature. **No change needed.**

### nomenklatura

- `nomenklatura/matching/logic_v2/names/analysis.py:44` — replace `replace_org_types_compare(form, normalizer=prenormalize_name)` with `replace_org_types_compare(form)`.
- `nomenklatura/matching/logic_v2/names/analysis.py:62` — replace `tag_person_name(sname, normalize_name, any_initials=is_query)` with `tag_person_name(sname, infer_initials=is_query)`. Drop the now-unused `normalize_name` / `prenormalize_name` imports if they become unreferenced.
- `nomenklatura/matching/erun/names.py:22` — `replace_org_types_compare(string)` already uses the new signature. No change needed.
- `tests/matching/test_symbol_pairings.py` — ~14 `Symbol(Symbol.Category.NAME, <int>)` / `Symbol.Category.NUMERIC, <int>)` constructions. The `Symbol(...)` calls still work (the constructor stringifies ints), but any `symbol.id == <int>` assertions or IDs passed as keys need to become `<int-as-str>`. Line 315 explicitly asserts `pairing.matches[0].symbol.id == 1` — change to `== "1"`.

### yente

- `yente/data/util.py:62` — replace `replace_org_types_compare(norm, normalizer=prenormalize_name)` with `replace_org_types_compare(norm)`.
- `yente/data/util.py` also uses `tag_person_name` / `tag_org_name` — audit those callsites for `normalizer=` / `any_initials=` args and drop/rename accordingly.
- Reindex: QID `Symbol.id` values now carry the `Q` prefix. If yente indexes symbol IDs directly (`f"{cat.value}:{sym.id}"`), the string space shifts. Plan a full reindex on deploy.

### zavod / opensanctions

No known callsites that use the changed APIs directly. Audit on
`rigour` bump.

## Version / timing

- Ships in rigour **1.9.0** (tentative — pin in the release commit).
- Coordinated-update ordering: bump rigour → bump FTM (probably no
  edits required) → bump nomenklatura + edit two callsites → bump
  yente + edit one callsite and plan a reindex → bump zavod.

## Non-breaking changes worth knowing about

- **`rigour.names.tokenize` Python `tokenize_name` is unchanged.** A
  Rust port exists internally (`rust/src/names/tokenize.rs`) but
  isn't exposed via PyO3 — Python callers keep the existing
  implementation.
- **`rigour.text.phonetics.metaphone` / `.soundex`** are Rust-backed
  now; output is identical (same upstream algorithm).
- **`ascii_text` / `latinize_text`** are Rust-backed via ICU4X; `pyicu`
  is no longer a dependency. Output should be identical for all
  covered scripts.
- **`_core.pyi` ships with `py.typed`**, so downstream `mypy
  --strict` sees the Rust-extension types transparently.

## When to ship

Coordinated release (one PR per repo) is easier to reason about
than staggered. Use this doc as the review checklist.
