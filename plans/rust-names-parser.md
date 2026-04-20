---
description: End-to-end architecture for the Rust name-analysis pipeline across rigour, FTM, nomenklatura, and yente — defines the `analyze_names` entry point that replaces the two near-duplicate `entity_names()` implementations
date: 2026-04-19
tags: [rigour, followthemoney, nomenklatura, yente, rust, names, analyze-names, api-design]
---

# Rust name-parsing: end-to-end architecture

This document zooms into what `rust.md` calls Phase 5 — the single `analyze_names`
FFI entry point — and fixes its contract against its real consumers. It is the
**cross-stack** view: rigour is the name engine, but the shape of that engine is
determined by what nomenklatura and yente need out the other side.

Related plans:
- `rust.md` — umbrella Rust port plan; Phase 5 is this work.
- `rust-normalizer.md` — flag-based `normalize()` replaces the `normalizer=`
  callback argument that both current `entity_names()` paths pass around.
- `rust-transliteration.md` — ICU4X-backed `ascii_text`/`latinize_text` that
  powers `NamePart.ascii` / `.comparable` / `.metaphone`.

## Motivation

Name analysis is duplicated. There are two near-identical `entity_names()`
functions in the stack:

| Callsite | File | Purpose |
|----------|------|---------|
| nomenklatura matcher | `nomenklatura/matching/logic_v2/names/analysis.py` | Build `Name` objects for matching both sides of a comparison |
| yente indexer       | `yente/data/util.py` (`entity_names`)              | Build `Name` objects to flatten into ES fields (`name_parts`, `name_phonemes`, `name_symbols`) |

Yente's own comment flags it: *"this does ca. the same thing as `logic_v2.names.analysis`.
Should we extract that into followthemoney or has it not yet stabilised enough?"*

Both paths:

1. Map schema → `NameTypeTag` (PER/ORG/ENT/OBJ/UNK) via FTM's `schema_type_tag`.
2. For PER: `remove_person_prefixes(raw)`.
3. `prenormalize_name(raw)` → `form`.
4. For ORG/ENT: `replace_org_types_compare(form, normalizer=prenormalize_name)`.
5. Construct `Name(raw, form=form, tag=type_tag)`.
6. Call `tag_org_name(name, normalize_name)` or
   `tag_person_name(name, normalize_name, infer_initials=is_query)`.

They differ in small but real ways (collected in *Divergences* below). Every one of
those differences is either an outright bug in one path or a policy decision that
should be made once. The Rust port is the moment to pick one canonical pipeline.

Secondary motivation: **performance**. Each call above is a separate Python→Rust
boundary crossing once the Rust port lands. For a large yente reindex or a
nomenklatura scoring pass, that's tens of millions of crossings. The
`fafo-rust` lesson applies: move the whole pipeline behind a single coarse
FFI call.

## Target architecture

```
┌────────── followthemoney ──────────┐   ┌──── rigour ────┐   ┌─── Rust ────┐
│                                    │   │                │   │             │
│  schema_type_tag(schema)           │   │                │   │             │
│  PROP_PART_TAGS                    │   │                │   │             │
│                                    │   │                │   │             │
│  entity_names(entity, props=None)  │   │                │   │             │
│    ├─ pick main-name props         │   │                │   │             │
│    │   (default: all name-typed)   │   │                │   │             │
│    ├─ always harvest part-tag props│   │                │   │             │
│    │   → dict[NamePartTag, [str]]  │   │                │   │             │
│    ├─ pick type_tag from schema    │   │                │   │             │
│    └─ call analyze_names(...) ─────┼──▶│ analyze_names  │──▶│ _core:      │
│                                    │   │   (Python      │   │ analyze_    │
│                                    │   │    wrapper)    │   │  names      │
│  returns Set[Name]                 │◀──┼──── Set[Name] ◀┼───│  Set[Name]  │
│                                    │   │                │   │             │
│  consumed by:                      │   │                │   │             │
│    ├─ nomenklatura (matching)      │   │                │   │             │
│    └─ yente (indexing + flatten)   │   │                │   │             │
│                                    │   │                │   │             │
└────────────────────────────────────┘   └────────────────┘   └─────────────┘
```

FTM owns the property-extraction layer. Rigour owns the name engine. Downstream
consumers (nomenklatura, yente) import `entity_names` directly from FTM — there
are no per-repo adapter copies.

### What lives where

**followthemoney** owns the entity → strings projection:
- `schema_type_tag(schema) -> NameTypeTag` (already lives here).
- `PROP_PART_TAGS: tuple[tuple[str, NamePartTag], ...]` (already lives here).
- **New:** `entity_names(entity, props=None, *, infer_initials=False,
  phonetics=False, numerics=False, consolidate=False) -> set[Name]` —
  reads properties off the entity, packages them into rigour's input shape,
  and forwards to `rigour.names.analyze_names`. This is the unified
  replacement for the two near-duplicate `entity_names()` functions in
  nomenklatura and yente.
- All three of these are pure FTM concerns: rigour has no schema model and
  no concept of property names.

**rigour** owns the name engine:
- `analyze_names(names, type_tag, part_tags, *, infer_initials=False,
  phonetics=False, numerics=False, consolidate=False) -> set[Name]` —
  single public API (Phase 5). Accepts plain strings + a
  `Mapping[NamePartTag, Sequence[str]]`. Never sees `EntityProxy`, never
  imports FTM.
- The primitives that underpin it (`tokenize_name`, `prenormalize_name`,
  `remove_person_prefixes`, `remove_org_prefixes`, `replace_org_types_compare`,
  `tag_org_name`, `tag_person_name`) stay importable because downstream code
  and tests still use them individually. Their `normalizer=` parameter goes
  away per `rust-normalizer.md`.

**nomenklatura** imports `entity_names` from FTM. Its
`logic_v2/names/analysis.py` collapses to a re-export plus the existing
`@lru_cache(maxsize=200)` (cache is load-bearing for cross-matching where one
query entity compares against many candidates).

**yente** imports `entity_names` from FTM. Its `yente/data/util.py:entity_names`
becomes a re-export; the flattening to `name_parts` / `name_phonemes` /
`name_symbols` stays in `indexer.py:build_indexable_entity_doc` as today.

### The `analyze_names` contract

```python
# rigour/names/analysis.py  (thin Python wrapper around rigour._core._analyze_names)
def analyze_names(
    names: Sequence[str],
    type_tag: NameTypeTag,
    part_tags: Mapping[NamePartTag, Sequence[str]] = {},
    *,
    infer_initials: bool = False,
    phonetics: bool = False,
    numerics: bool = False,
    consolidate: bool = False,
) -> set[Name]:
    ...
```

Rationale for the shape:

- **Single `part_tags` dict.** The caller has already done the FTM-side
  projection — by the time we reach rigour, there are no property names,
  just pre-classified string bags keyed by `NamePartTag`. Marshals across
  PyO3 as a `HashMap<NamePartTag, Vec<String>>`; enum variant discrimination
  is cheap. Open-ended: adding a new `NamePartTag` does not require an API
  change here.
- **No `normalizer=` callback.** Per `rust-normalizer.md`. The inside of
  `analyze_names` picks the right normalisation for each step itself.
- **`infer_initials` instead of `is_query`.** nomenklatura historically
  called this `is_query` — describing the caller, not the behaviour.
  What the flag actually controls in `tag_person_name(infer_initials=...)`:
  with it off, only parts already tagged GIVEN/MIDDLE (from
  `part_tags`) get mapped to `Symbol.INITIAL` when they're a single
  character; with it on, *any* single-character latin part becomes an
  INITIAL symbol. That's useful for free-text query sides where "J Smith"
  arrives without a label on "J". The tagger parameter already uses
  `infer_initials`; `analyze_names` adopts the same name for
  end-to-end consistency.
- **`weak_alias` and the weak-alias-as-name policy live in the FTM
  adapter**, not in `analyze_names`. See Divergences row #4: FTM's
  `entity_names` both extends `names` with `weakAlias` values *and*
  populates `part_tags[NICK]` with them. Rigour stays pure — `names` is
  just names, `part_tags` is just annotation.
- **`consolidate` is opt-in, default `False`.** When `True`, the returned
  set has `Name.consolidate_names` applied to it — short names that are
  substrings of longer names in the same set are dropped. This is a
  *matching-side* policy (prevents a short "John Smith" from spuriously
  matching a query "John K Smith" when the longer candidate "John R
  Smith" would correctly mismatch); the indexer must not use it or it
  loses recall on partial-name searches. Folding consolidation into the
  same FFI call avoids an extra Python→Rust round-trip in nomenklatura's
  matcher, which is the call site that needs it. See Divergences row #9.
- **`phonetics` is opt-in, default `False`.** When `True`, `NamePart.metaphone`
  is populated (the jellyfish/rphonetic `metaphone` of the part's ASCII form,
  gated on `latinize && !numeric && len(ascii) > 2`). When `False`, the field
  stays `None` and the phonetics crate isn't called. Matchers and indexers
  that feed `name_phonemes` into Elasticsearch or into Levenshtein-on-phonemes
  comparisons pass `True`; lightweight callers (display pipelines, entity
  export, enrichment that doesn't score on phonemes) leave it off and save
  a metaphone call per part.
- **`numerics` is opt-in, default `False`.** When `True`, the post-tagger
  `_infer_part_tags` pass adds `Symbol(NUMERIC, int_value)` for numeric-
  looking name parts that the AC tagger's ordinal list didn't already
  match (e.g. large arbitrary numbers like `"123456789"` in `"123456789
  Batallion"`, not the cardinals/ordinals the AC list covers). When
  `False`, parts still get their `NamePartTag.NUM` tag (cheap structural
  info) but no NUMERIC symbol is added — matchers that use numeric-symbol
  overlap for disambiguation pass `True`; callers that only need the tag
  structure leave it off.
- **Return type is `set[Name]`.** Both current callsites use a set, and
  deduplication happens inside `analyze_names` anyway, so returning one is
  truth in advertising. Hashing is by the `Name` object's identity for now
  (Python `set` semantics); if duplicate-merge-across-ingest becomes a need
  later we revisit.

### Rust-side pipeline (one FFI call)

Inside Rust, for a single `analyze_names` invocation:

```text
for raw in names:
    if type_tag == PER:
        raw = remove_person_prefixes(raw)           # Phase 3
    form = prenormalize_name(raw)                    # Phase 1 (casefold)
    if type_tag in (ORG, ENT):
        form = replace_org_types_compare(form)       # Phase 3
        form = remove_org_prefixes(form)             # Phase 3
    if form in seen: continue
    seen.insert(form)
    # Phase 2 construction. ascii/comparable/latinize/numeric/integer are
    # always eager (cheap). metaphone is eager iff `phonetics` — otherwise
    # NamePart.metaphone returns None.
    name = Name::new(raw, form, type_tag, phonetics)
    for (part_tag, values) in part_tags:
        for v in values:
            name.tag_text(prenormalize_name(v), part_tag)
    if type_tag in (ORG, ENT):
        tag_org_name(&mut name)                      # Phase 4 AC tagger
    if type_tag == PER:
        tag_person_name(&mut name, infer_initials)   # Phase 4 AC tagger
    infer_part_tags(&mut name, numerics)             # LEGAL/NUM/STOP tags;
                                                     # numeric Symbols iff numerics
    names.push(name)
if consolidate:
    names = consolidate_names(names)                 # drop substring-dominated names
return names
```

No Python callbacks. No FFI crossings during the loop. Everything the pipeline
needs is either embedded data (AC tables, org types, prefixes, symbols) or
precomputed on `NamePart` at construction time (ascii, comparable, plus
metaphone if `phonetics=True`).

## The FTM-side adapter

The single canonical adapter lives in `followthemoney.names`:

```python
# followthemoney/names.py
from functools import lru_cache
from typing import Mapping, Optional, Sequence, Set
from followthemoney import registry, EntityProxy
from rigour.names import Name, NameTypeTag, NamePartTag, analyze_names
from followthemoney.schema import Schema


def schema_type_tag(schema: Schema) -> NameTypeTag:
    ...  # unchanged


# Property → annotation tag(s). Used regardless of `props` selection;
# these properties never contribute to the list of "main" names, they only
# annotate parts inside the main names.
#
# A property can map to MULTIPLE tags — used for genuinely ambiguous props
# where a value has semantic overlap with more than one structural role. The
# clearest case: `fatherName` / `motherName` values should tag parts that
# look like MIDDLE names (Slavic patronymic convention, where the father's
# name sits between given and family) AND parts that look like FAMILY names
# (Hispanic convention, where the father's name IS a family name). Rather
# than detect locale or force the crawler to choose, tag both — the matcher
# uses whichever alignment actually fires.
#
# NOTE: `secondName` is an ambiguous term (some datasets use it for a
# second given name, others for a second surname). We collapse it to MIDDLE
# to match historical behaviour — deliberate, not accidental. Don't
# "fix" this to FAMILY without a migration plan.
PART_TAG_PROPS: tuple[tuple[str, tuple[NamePartTag, ...]], ...] = (
    ("firstName",   (NamePartTag.GIVEN,)),
    ("lastName",    (NamePartTag.FAMILY,)),
    ("secondName",  (NamePartTag.MIDDLE,)),   # see NOTE above
    ("middleName",  (NamePartTag.MIDDLE,)),
    ("fatherName",  (NamePartTag.MIDDLE, NamePartTag.FAMILY)),
    ("motherName",  (NamePartTag.MIDDLE, NamePartTag.FAMILY)),
    ("title",       (NamePartTag.HONORIFIC,)),
    ("nameSuffix",  (NamePartTag.SUFFIX,)),
    ("weakAlias",   (NamePartTag.NICK,)),
)


# TEMPORARY: LRU cache is scaffolding to compensate for today's slow Python
# name pipeline. Drop once rust.md Phase 5 lands and the single-FFI
# analyze_names is fast enough to not need it. Intentionally hacky — do not
# build features on top of this cache.
@lru_cache(maxsize=200)
def entity_names(
    entity: EntityProxy,
    props: Optional[Sequence[str]] = None,
    *,
    infer_initials: bool = False,
    phonetics: bool = False,
    numerics: bool = False,
    consolidate: bool = False,
) -> Set[Name]:
    """Build Name objects from an FTM entity.

    `props` selects which properties contribute to the list of "main" names:
    - `None` (default): all `name`-typed matchable properties (covers
      `name`, `alias`, `previousName`, and any schema-specific name props).
    - Explicit list: e.g. `["name"]` to restrict to the primary name, or
      `["alias"]` to look at aliases only.

    Part-tag properties (firstName, lastName, fatherName, …) are *always*
    harvested regardless of `props` — they annotate name parts, they do
    not contribute standalone names. Exception: `weakAlias` is both a
    standalone name and a NICK annotation on other names.

    `consolidate=True` drops short names that are substrings of longer
    names in the result set (matching-side policy — avoids a short alias
    masking a longer-name mismatch). Indexers should leave this as
    `False` to preserve partial-name recall.
    """
    type_tag = schema_type_tag(entity.schema)

    if props is None:
        names = list(entity.get_type_values(registry.name, matchable=True))
    else:
        names = []
        for p in props:
            names.extend(entity.get(p, quiet=True))

    # weakAlias is also a standalone name (matches yente's current behaviour;
    # strictly additive vs. nomenklatura's current behaviour — see Divergences
    # row #4).
    names.extend(entity.get("weakAlias", quiet=True))

    part_tags: dict[NamePartTag, list[str]] = {}
    for prop, tags in PART_TAG_PROPS:
        values = entity.get(prop, quiet=True)
        if not values:
            continue
        for tag in tags:
            part_tags.setdefault(tag, []).extend(values)

    return analyze_names(
        names,
        type_tag,
        part_tags,
        infer_initials=infer_initials,
        phonetics=phonetics,
        numerics=numerics,
        consolidate=consolidate,
    )
```

The `@lru_cache(maxsize=200)` exists only because today's Python pipeline is
expensive enough that nomenklatura's cross-matching (one query × many
candidates) would otherwise recompute names per comparison. The cache is
explicitly temporary scaffolding: once `rust.md` Phase 5 ships the
single-FFI `analyze_names`, name construction is cheap enough per call that
the cache is no longer load-bearing, and it comes out. Document this inline
so nobody reasons about it as a stable mechanism. It is keyed by
`EntityProxy.__hash__` (ID-only, not property-aware) — preserve the existing
warning comment from nomenklatura when hoisting.

## What the consumers do with the returned `Name`s

### nomenklatura (matching)

Uses `Name` as the primary unit of comparison. Accesses `.parts`, `.spans`,
`.symbols`, `.comparable`, `.tag` downstream. Everything is already computed,
so attribute access is a cheap Rust→Python field read.

`nomenklatura/matching/logic_v2/names/analysis.py` shrinks to:

```python
from followthemoney.names import entity_names  # re-export or direct use
```

All existing callers of the old `entity_names(type_tag, entity, prop, is_query)`
signature update to the new `entity_names(entity, props=[prop] if prop else None,
infer_initials=is_query, phonetics=True, numerics=True)` shape. The matcher
needs both phoneme overlap and numeric-symbol overlap, so it opts in on both.
The `type_tag` parameter goes away — FTM infers it from the schema, and the
old call sites always computed it from the entity anyway.

### yente (indexing)

Uses `Name` to produce three flat field lists for Elasticsearch:
- `name_parts`: `part.form` ∪ `part.comparable` for every part of every name.
- `name_phonemes`: `part.metaphone` for parts where it exists and `len > 2`.
- `name_symbols`: `index_symbol(sym)` = `f"{sym.category.value}:{sym.id}"` for
  every symbol of every name, filtered by `Symbol.is_matchable` (moved from
  yente into rigour — see Divergences row #7).

`yente/data/util.py:entity_names` shrinks to:

```python
from followthemoney.names import entity_names

# Indexer call
entity_names(entity, phonetics=True, numerics=True)
```

Yente needs `phonetics=True` because `name_phonemes` is an ES field derived
from `part.metaphone`, and `numerics=True` because `name_symbols` includes
NUMERIC IDs from large-number parts that the AC ordinal list doesn't cover.
Both have always been implicit in today's Python pipeline; the new
`analyze_names` makes them explicit opt-ins.

The flattening in `build_indexable_entity_doc` is untouched — it is yente's
business to decide what ends up in ES, and a couple of `for` loops over a
small Name set isn't a bottleneck.

## Divergences between today's two implementations — resolution

These are the real behavioural differences to reconcile when unifying. Each
gets one answer; the Rust `analyze_names` will behave exactly that way for
everyone.

| # | Behaviour | nomenklatura today | yente today | Resolution |
|---|-----------|--------------------|-------------|------------|
| 1 | Dedup names by `form` | yes | no | **Dedup.** Yente currently double-indexes trivially equivalent names (e.g. `"IBM"` and `"IBM "`); no real signal gained, and ES fields are sets anyway downstream. Cheap correctness win. |
| 2 | `remove_org_prefixes` | yes | **no** | **Run it.** Yente's omission looks like a simple oversight — stripping a leading "The" is plainly the right thing for both matching and indexing. |
| 3 | Tag parts from `PROP_PART_TAGS` (firstName→GIVEN etc.) | yes | **no** | **Run it.** Yente currently discards tag information that FTM already knows. For matching and for symbol-driven index tokens, this is information it would otherwise re-infer less accurately. |
| 4 | `weakAlias` added to the `names` list | no | **yes** | **Keep yente's behaviour as the unified rule: treat `weakAlias` both as a full name AND as NICK-tagged parts on the main names.** Weak aliases *are* names (a crawler explicitly asserted so); they deserve their own `Name` object. Tagging them as NICK on other names is additive — FTM's `entity_names` populates both `names` and `part_tags[NICK]` with the weak-alias values. Nomenklatura gains coverage; yente keeps coverage. |
| 5 | `is_query` / `any_initials` | yes (matching) | n/a (indexing never has a query side) | **Parameter stays but renamed to `infer_initials`** to describe the behaviour, not the caller. Default `False`; matcher sets `True` only on the query entity. Indexer always passes `False`. |
| 6 | `@lru_cache(maxsize=200)` at the adapter | yes | no | **Cache lives on the FTM-side `entity_names` as temporary scaffolding** — until Phase 5 of `rust.md` makes the pipeline fast enough to drop it. Keyed by `EntityProxy.__hash__` (ID-only). Do not build features on top of this cache. |
| 7 | `Symbol.Category.INITIAL` treated as non-matchable | n/a | yes (yente's `NON_MATCHABLE_SYMBOLS`) | **Move the `is_matchable` predicate onto `Symbol` in rigour** — it's semantic data about the symbol category, not an indexer policy. Yente keeps using it for index filtering; nomenklatura gets it for free if ever relevant. |
| 8 | `fatherName` / `motherName` tagging | PATRONYMIC / MATRONYMIC | same | **Feed `fatherName` and `motherName` values into both `part_tags[MIDDLE]` and `part_tags[FAMILY]`.** These properties are genuinely ambiguous — Slavic sources use them as patronymics (structurally MIDDLE, sitting between given and family), Hispanic sources use them as additional family names (structurally FAMILY). Rather than detect locale or force crawlers to choose, tag both. The matcher aligns whichever interpretation actually fires against the candidate. No `PATRONYMIC`/`MATRONYMIC` tags produced by the FTM adapter (they remain in the `NamePartTag` enum for backwards compatibility and any future hand-tagged use). No per-call override kwargs — the multi-tag is the whole policy. |
| 9 | `Name.consolidate_names` — drop short substring names | called *after* `entity_names` in `logic_v2/names/match.py:234-235` | **not called** | **Fold in as an opt-in `consolidate` flag on `entity_names` / `analyze_names`, defaulting `False`.** The matcher passes `True` (and drops the current explicit `Name.consolidate_names(...)` calls in `match.py`); the indexer leaves it as `False` to preserve partial-name recall in ES. Folding it inside the single FFI call keeps Phase 5's "one crossing per entity" property even for the matching side. Zavod's ExportPolicy overrides (e.g. `test_consolidate_names_never_remove_ofac_names`) are a separate dataset-level policy that consumes the primitive — unaffected by this move. |

Items 2, 3, 4 are the biggest real changes: yente's indexed representation
gains org-prefix stripping, property-tag hints, and weak-alias-as-name. These
should be called out in the yente PR as intentional index-shape changes (minor
recall improvements, no recall regressions expected).

## What does NOT change

- **`NamePartTag`, `NameTypeTag`, `Symbol.Category`** — identical enums, just
  exposed from Rust via PyO3. All existing imports keep working.
- **`Name` attribute surface** — `.parts`, `.spans`, `.symbols`, `.comparable`,
  `.tag`, `.original`, `.form`, `.lang` all still there. See `rust.md` Phase 2
  for the exact shape.
- **FTM's `schema_type_tag` and `PROP_PART_TAGS`** — stay where they are. No
  new rigour ⇄ FTM dependency.
- **Yente's flattening logic** — the `for name in entity_names(entity): for
  part in name.parts: ...` stays Python. The only change in the indexer is
  that `entity_names` now calls `analyze_names` under the hood.

## Performance contract

Two measurable wins drop out of this unification:

1. **FFI crossings per entity**: from O(names × (1 prenorm + 1 org-replace + 1
   prefix + 1 tagger + K part-tags)) down to **one** per entity
   (`analyze_names`). On a 100M-name reindex this is the difference between
   ~1B crossings and ~10M.
2. **Python object overhead**: `Name`/`NamePart`/`Symbol` become PyO3 classes
   with Rust-owned storage (~200–400 bytes each vs ~1–5KB for Python objects).
   See `rust.md` §Goals bullet 4.

Benchmarks to pin before declaring Phase 5 done:

- `analyze_names` on a realistic nomenklatura batch (1k entities mixed
  PER/ORG): target ≥5× speedup vs the current Python pipeline.
- Yente full reindex on the default sanctions + PEP datasets: wall-clock
  improvement + entity/second throughput.
- Matching: `entity_names`-heavy scoring pass (logic_v2 cross-matcher) —
  target ≥3× speedup, limited by the downstream matching work that stays
  Python.

## Phasing and rollout

Phase 5 in `rust.md` is the landing point. Incremental staging:

1. **Land the rigour-side API as a Python shim first.** Once Phases 1–4 are
   in, `rigour.names.analyze_names(names, type_tag, part_tags, *,
   infer_initials)` can be implemented as Python glue calling the existing
   Rust-backed primitives one by one. This lets consumers migrate before
   Phase 5's single-FFI version exists — the API contract is the same.
2. **Hoist the adapter into FTM.** Add `followthemoney.names.entity_names`
   with the signature above, keep `schema_type_tag` and `PROP_PART_TAGS` as
   they are (the latter becomes an implementation detail of the adapter but
   stays exported for compatibility). Move `is_matchable` onto
   `rigour.names.Symbol`.
3. **Migrate nomenklatura.** Replace the body of
   `nomenklatura/matching/logic_v2/names/analysis.py:entity_names` with a
   re-export from FTM (or update callers directly). Delete the now-unused
   `replace_org_types_compare(..., normalizer=...)` callsite. Callers pass
   `phonetics=True, numerics=True` on both sides (matching's scoring uses
   both), `infer_initials=True` only on the query side, and
   `consolidate=True` on both the query and candidate call (matching the
   current behaviour of `match.py:234-235`). Drop the explicit
   `Name.consolidate_names(...)` calls from `match.py` — the flag on
   `entity_names` replaces them.
4. **Migrate yente.** Replace `yente/data/util.py:entity_names` with a
   re-export from FTM. Indexer passes `phonetics=True, numerics=True`
   (they feed `name_phonemes` and `name_symbols` in ES). Drop yente's
   `NON_MATCHABLE_SYMBOLS` + `is_matchable_symbol` (use
   `Symbol.is_matchable`). This is where the Divergences items 2/3/4
   actually change behaviour — expect a small set of fixture-test
   updates around org-prefix stripping, property-tagged parts, and
   weak-alias-as-name.
5. **Collapse the Python shim into the single Rust call** (Phase 5 proper).
   The API does not change; only the implementation moves. Benchmarks
   validate the crossing-reduction claim.

Between steps 1 and 5, both consumers already go through a *single* Python
function call (`entity_names` → `analyze_names`), so the call-site refactor
is locked in. Step 5 is a pure implementation swap behind the rigour API and
can land independently.

### Follow-up: rewire the tagger's alias pipeline onto `tokenize_name`

**Done.** The `rust/src/names/tagger.rs` alias builder now calls
`tokenize_name` directly (single source of truth for category /
skip-char handling) and drops the ad-hoc `TOKENIZE_SKIP_CHARS`
pre-strip. As a consequence the `cleanup` argument was removed from
the tagger's public API end-to-end — `tokenize_name` subsumes its
role. Aligning the tagger with the runtime haystack pipeline also
fixed a latent bug where `Cleanup::Strong` deleted CJK Lm and Mc
chars that `tokenize_name` keeps (e.g. `ー` in `ウラジーミル`).

## Open questions

1. **`lang` hint threading.** `Name` has an optional `lang`. Neither current
   adapter passes one; both datasets have per-name language info (FTM's
   language-scoped names, yente's dataset language defaults). Should
   `analyze_names` accept `langs: Sequence[Optional[str]]` paired 1:1 with
   `names`? Deferred — would unlock per-language tokenisation tweaks but
   nobody has asked for it yet.
2. **Weak-alias-as-name vs weak-alias-as-tag only**: the resolution above says
   "do both" (FTM's adapter feeds weakAlias into both `names` and
   `part_tags[NICK]`). Double-check matcher behaviour — a weak alias
   promoted to a full `Name` must not also be tagged NICK *on itself*
   (that would create a self-referential token). Trivial guard inside
   `analyze_names` but needs a test.
3. **`pick_names` in yente (`yente/data/util.py:83`)** uses `levenshtein` in a
   Python loop to pick centroids. Out of scope for this plan but noted — it's
   a good candidate for the `pick_name` Rust port sketched in `rust.md` Phase
   6.
4. **`secondName` demotion.** `secondName` is collapsed to
   `NamePartTag.MIDDLE` in the FTM adapter. The term is ambiguous across
   sources (second given vs second surname). If we ever gain clear per-
   source signal, revisit — for now, MIDDLE is the least-bad default and
   matches current FTM behaviour. Do not change without a migration plan.

## Resolved (kept for the record)

- **Output ordering.** Not an objective. FTM properties have no strict order;
  `set[Name]` return type is fine and downstream consumers already treat the
  result as a set.
- **Provenance of deduplicated names.** Dedup is on `form` and drops
  information about which property a name came from. Downstream code does
  not care today. Add provenance later if a consumer grows a real need.
- **`infer_initials` on the indexing side.** Initials are a logic-v2 matching
  concern only. Yente's indexer always passes `False`; no symmetry gap to
  worry about because yente doesn't use initial-based matching.
- **Locale detection for `fatherName` / `motherName`.** Avoided entirely.
  The multi-tag resolution in Divergences row #8 (tag both MIDDLE and
  FAMILY) sidesteps needing to know the data source's naming convention.
- **FTM taking on the rigour Rust extension.** Not a concern — FTM is
  rigour's primary consumer; anything in rigour is there to serve FTM.
