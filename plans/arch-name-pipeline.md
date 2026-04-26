---
description: Architecture of rigour's name-analysis pipeline — Symbol/Name/NamePart object graph, the analyze_names single-FFI entry point, pair_symbols, and the pick_name family.
date: 2026-04-26
tags: [rigour, names, analyze, symbols, pick-name, architecture]
---

# Name pipeline: architecture

The rigour name pipeline takes raw name strings from an entity and
produces tagged `Name` objects that downstream matchers and indexers
consume. The pipeline lives end-to-end in Rust, exposed to Python via
PyO3. This document describes the object graph, the analyze and
pick paths, and the cross-stack adapter pattern.

For the Rust core conventions (build, FFI, data embedding) see
`arch-rust-core.md`. For text normalisation and transliteration
primitives see `arch-text-normalisation.md`.

## The object graph

Four pyclasses, all defined in `rust/src/names/`:

- **`Name`** (`names/name.rs`). Top-level. Owns the original input
  string, a normalised `form`, a `NameTypeTag` (PER / ORG / ENT /
  OBJ / UNK), an optional `lang` hint, an immutable `parts` tuple
  of `NamePart`, and a growing `spans` list of `Span`. Equality
  and hashing are over `form` — so two `Name`s with the same
  normalised form collapse in a `set`, regardless of tag mutation
  on either side.
- **`NamePart`** (`names/part.rs`). One token. Eager fields:
  `form`, `index`, `tag` (mutable), `latinize`, `numeric`,
  `ascii`, `integer`, `comparable`, `metaphone`. The `tag` mutates
  during analysis (the tagging pipeline writes it after
  construction); no other cached field depends on `tag`, so
  mutation doesn't invalidate anything. String fields are stored
  as `Py<PyString>` so attribute reads from Python are
  zero-allocation INCREFs.
- **`Span`** (`names/part.rs`). A contiguous group of parts
  carrying a single `Symbol`. Owns cloned `NamePart` references
  rather than indices — once a `Span` reaches Python it has no
  back-pointer to its parent `Name`, and `NamePart` is `Clone`
  and small.
- **`Symbol`** (`names/symbol.rs`). A `(SymbolCategory, id)` pair
  the tagger attaches to spans: `NAME:Q4925477` for a recognised
  person name, `ORG_CLASS:LLC` for a legal form, `INITIAL:j` for
  a single-letter stand-in.

`NamePartTag` and `NameTypeTag` are sealed Rust enums exposed as
pyclasses. The Python-side `tag.py` re-exports them and adds a
small set of frozenset constants (`INITIAL_TAGS`, `WILDCARDS`,
`GIVEN_NAME_TAGS`, `FAMILY_NAME_TAGS`, `NAME_TAGS_ORDER`) for the
membership checks downstream code performs.

## Symbol: `Arc<str>` IDs with a global interner

```rust
pub struct Symbol {
    category: SymbolCategory,   // sealed enum, repr(u8)
    id: Arc<str>,               // refcount in heap header
}
```

All distinct id strings funnel through a global `intern()` backed
by `LazyLock<RwLock<HashMap<Box<str>, Arc<str>>>>`. One heap
allocation per distinct string, shared via `Arc` refcount.

### Why not `u32` IDs

A `u32`-per-Symbol design with per-category string tables would
shrink Symbol from ~24 bytes to 8. At matching-index scale
(~100-200k unique IDs, millions of Symbol instances) that's a
real saving. Rejected because:

1. **The `NAME` category has heterogeneous IDs.** Wikidata QIDs,
   X-prefixed manual overrides, and possible future ID schemes
   share the conceptual NAME bucket but use different id
   conventions. Splitting them into per-source categories breaks
   the abstraction; bit-space partitioning is ugly and caps QIDs
   at 2³¹.
2. **Simplicity cost.** Tables, reverse lookups, and
   category-aware dispatch in the `Symbol.id` getter outweigh the
   ~30-50% memory saving.
3. **`Arc<str>` is idiomatic.** Any maintainer reads it
   instantly; a `u32`-table scheme needs explanation every time
   it's touched.

The escape hatch if memory ever dominates: a per-process Symbol
registry that assigns each distinct `(category, id)` a dense
`u32` at first construction and reduces `Symbol` to a single
word. Possible end state, not currently scheduled.

### Symbol invariants

- `Symbol.id` is always a string. Numeric-source IDs (Wikidata
  QID integers, ordinal numbers) are stringified at construction.
  This is a breaking change from pre-port Python, where
  `Symbol.id` was `int | str`.
- `SymbolCategory` is a sealed pyclass enum. Adding a variant is
  a cross-stack change; downstream consumers (matchers, indexers)
  branch on it.
- `Symbol.is_matchable` is a category-level predicate (currently
  excluding `INITIAL` from "this overlap is real evidence"
  contexts). Lives on the Rust side so all callers see the same
  rule.

## `analyze_names`: single-FFI pipeline

`rigour.names.analyze_names` is the canonical entry point.
Downstream consumers (FTM's `entity_names`, in turn used by
nomenklatura and yente) call it once per entity and get back a
`set[Name]` ready for matching.

```python
def analyze_names(
    type_tag: NameTypeTag,
    names: Sequence[str],
    part_tags: Optional[Mapping[NamePartTag, Sequence[str]]] = None,
    *,
    infer_initials: bool = False,
    symbols: bool = True,
    phonetics: bool = True,
    numerics: bool = True,
    consolidate: bool = True,
    rewrite: bool = True,
) -> Set[Name]:
```

One PyO3 crossing per call regardless of how many names or part
tags are supplied. The Rust implementation runs in
`rust/src/names/analyze.rs`:

1. **Prefix strip** (PER → person honorifics, ORG/ENT → article
   prefixes; gated by `rewrite`).
2. **Casefold** to produce the working `form`.
3. **Org-type rewrite** (ORG/ENT only, gated by `rewrite`):
   replaces "GmbH" / "Aktiengesellschaft" / etc. with their
   canonical compare form.
4. **Dedup** by form — duplicates after normalisation collapse.
5. **`Name` + `NamePart` construction**, all derived properties
   eager.
6. **Apply `part_tags`** via `Name.tag_text` for each
   `(NamePartTag, [string])` entry. Multi-token values walk the
   parts looking for the token sequence (non-adjacent tolerated).
7. **PER `INITIAL` symbol preamble** (gated by `symbols` and
   `infer_initials`).
8. **Tagger match-and-apply** (gated by `symbols`): person tagger
   for PER, org tagger for ORG/ENT.
9. **`infer_part_tags` post-pass**: NUM/STOP/LEGAL promotion,
   ENT→ORG upgrade if the name carries enough ORG_CLASS
   evidence.
10. **`consolidate_names`** if requested: drop names that are
    structurally contained in longer names in the result.

### The flag surface

Each kwarg gates a specific behaviour and exists because some
caller wants to skip that work:

- `consolidate=False` for indexers that need to preserve
  partial-name recall (yente). Matchers keep the default.
- `phonetics=False` for callers that never read
  `NamePart.metaphone`.
- `symbols=False` to skip the AC tagger entirely — tokens and
  part tags still apply, just no `Name.symbols` / `Name.spans`.
- `numerics=False` to skip NUMERIC-symbol emission while keeping
  the cheaper `NamePartTag::NUM` promotion.
- `infer_initials=True` on the matcher's query side, where
  free-text input arrives without explicit `INITIAL` tags. Indexers
  and the candidate side default to False.
- `rewrite=False` to keep the literal input form (no honorific
  strip, no "Inc. → LLC" substitution) — useful for debugging the
  tagger and for callers indexing display forms.

### Cross-stack adapter

Schema-aware harvesting of strings from FTM entities lives in
followthemoney, not rigour:

- `followthemoney.names.entity_names(entity, props=None, ...)`
  reads name properties off the entity, projects them into the
  three positional args of `analyze_names` (`type_tag`, `names`,
  `part_tags`), and forwards the flag kwargs.
- nomenklatura's matcher and yente's indexer both call FTM's
  `entity_names` directly. The two near-duplicate `entity_names`
  implementations they used to keep are gone.

The split: rigour owns the name engine, FTM owns the
entity-to-strings projection, downstream consumers compose them.

## `pair_symbols`

`rigour.names.pair_symbols(query, result)` aligns the symbol
spans of two `Name`s into coverage-maximal pairings. Implementation
in `rust/src/names/pairing.rs`; Python wrapper in
`rigour/names/symbol.py`.

Used by matchers to skip Levenshtein on tokens the tagger has
already explained on both sides — Latin "Vladimir" and Cyrillic
"Владимир" both carrying the same `NAME:Q...` Putin symbol pair
without string comparison.

Each returned pairing is a tuple of non-conflicting `SymbolEdge`s
whose joint coverage is maximal within its scoring-equivalence
class. Coverings that cover the same parts with the same category
mix collapse to one; distinct category choices on the same parts
(e.g. a token carrying both `NAME` and `SYMBOL`) surface as
separate pairings.

A single empty pairing `[()]` is returned when neither name has
tagger output, when no symbol is shared, or when either name has
more than 64 parts. The 64-part cap is a bitset-width limit on
the alignment representation.

## `pick_name` family

`rigour.names.pick_name` is the per-entity display-name picker
called during OpenSanctions data export — chosen-display, not
matching. Implementation in `rust/src/names/pick.rs`. Three
public functions:

- **`pick_name(names)`** — single-name pick from a multi-script
  alias bag.
- **`pick_case(names)`** — best case-mix from inputs that are
  identical except for case.
- **`reduce_names(names)`** — casefold-deduplicate a list,
  keeping the best case variant per group.

Plus one Python-only helper:

- **`representative_names(names, limit, cluster_threshold=0.3)`**
  in `rigour/names/pick.py`. Reduces a bag of aliases to at most
  `limit` representatives without extreme information loss.
  Built on `pick_name` + `reduce_names` + a Levenshtein-based
  cluster pass; ports to Rust only if profiling justifies.

### `pick_name` algorithm

The contract is "given a bag of multi-script names referring to
the same entity, return the single best display string." The
input list is cleaned (strip + casefold-empty drop); the
implementation then:

1. **Computes per-name `latin_share`** — fraction of alphabetic
   chars that are Latin. Cyrillic and Greek score 0.3 (they
   transliterate cleanly), other scripts 0.0.
2. **Single-Latin short-circuit**: if exactly one name has
   `latin_share > 0.85` it wins without further work. This is
   the common case in heterogeneous sanctions data — one Latin
   name plus several script variants.
3. **Cross-script reinforcement**: each form also indexes its
   `ascii_text` transliteration (when available) as an
   additional vote with the same weight. This stacks votes
   across scripts on the ASCII cluster — three transliterations
   of "Putin" reinforce the Latin "Putin" against an
   under-represented Cyrillic original.
4. **Centroid scoring**: weighted Levenshtein similarity over
   unique surface forms, bucketed and aggregated. Tied scores
   break by first-appearance insertion order, not float-rounding
   accidents.
5. **Surface tiebreak**: within the winning form, pick by
   `(latin_share DESC, case_error_score ASC, alphabetical ASC)`.
   `case_error_score` is the heuristic that
   `pick_case` exposes as a public primitive.

### Algorithm details worth preserving

**Count-based O(M²) Levenshtein.** Pre-port Python enumerated
`combinations(entries, 2)` and accumulated into a
`defaultdict(float)`. For duplicate-heavy buckets (18 `"GAZPROM"`
+ 18 `"Gazprom"`) this did `C(36, 2) = 630` distance calls for a
score that depends on only one unique pair. The Rust port dedupes
first, then uses an algebraic identity: for entries with counts
`c_X, c_Y` and similarity `sim`, `edits[X] += c_X · (c_X-1) · w_X
+ c_X · c_Y · sim · w_X`. Same output, far fewer distance calls.

**Cross-script skip.** `pick_name` runs `text_scripts` over the
whole input bag upfront. If every input is in the same script,
cross-script reinforcement can't help — skip the transliteration
pipeline entirely. The flag is `cross_script: bool` inside the
main loop; the saving compounds on single-script alias bags.

**No synthetic title-case injection.** Pre-port Python used
`forms[form].append(name.title())` to inflate the centroid score
of whichever surface matched a title-cased variant. This produced
exact ties on balanced input that Python broke via accidental
IEEE-754 rounding order — non-deterministic, reorder-sensitive.
Replaced with the principled `case_error_score` heuristic in the
surface tiebreak. Output may differ from pre-port on tied-score
inputs; intentional functional-equivalence divergence.

**Intra-Rust transliteration cache.** Rust-internal callers of
`maybe_ascii` (via the older `ascii_text` path) don't go through
the Python wrapper's `@lru_cache`, so they'd otherwise pay the
full ICU4X cost on every call. A thread-local cap-N HashMap
inside the relevant Rust function absorbs this for any
Rust-internal caller — `pick_name`, `analyze_names`, the
tagger's alias-build path. See `arch-text-normalisation.md` for
the broader context.

### `pick_case` and `reduce_names`

Both moved to Rust as part of the same work. `pick_case` is also
used inside `pick_name`'s surface tiebreak; exposing it as a
standalone primitive means callers don't reimplement the case-
quality heuristic. The Python wrapper preserves the `ValueError`
on empty input that pre-port callers expect (Rust returns
`None`).

`reduce_names` deduplicates a name list by casefold, keeping the
best-case variant per group via `pick_case`. Order is preserved
by first-appearance of each casefolded key.

### `representative_names`

```python
def representative_names(
    names: List[str],
    limit: int,
    cluster_threshold: float = 0.3,
) -> List[str]
```

Reduces a bag of aliases to at most `limit` representatives.
Useful when a downstream process (e.g. building a search-index
query) wants to probe the alias space broadly under a budget cap.

The fast path: if `reduce_names(names)` already fits in `limit`,
return all of them as-is — clustering is only useful when there
are more distinct names than budget allows. When clustering does
run, it's farthest-point-first seed selection with threshold
stopping, then per-cluster `pick_name` so the returned rep is
the best display form of its group rather than whichever
outlier seeded it.

The function stays Python because the levenshtein primitive it
uses is Python (`rapidfuzz` opcodes gap — see
`arch-rust-core.md`). Port if profiling shows it hot.

### `pick_lang_name`

Thin language-filter wrapper over `pick_name` in
`rigour/names/pick.py`. Stays Python — not worth the FFI surface.
Not in `rigour.names.__all__`; callers import from
`rigour.names.pick` directly.

## `consolidate_names`

`Name.consolidate_names(names) -> set[Name]` drops short names
structurally contained in longer names in the same iterable.
Equality of two `Name`s is by `form` (insertion into a `PySet`
deduplicates), so case-only variants of the same name collapse
through set semantics regardless of containment logic.

PER names use a structural subset rule: every part of `other`
must have a (not-necessarily-adjacent) `comparable`-equal
counterpart in `self`. Non-PER (or PER fallback) uses substring
containment of `norm_form`.

The matcher uses `consolidate=True` to avoid scoring "John Smith"
against "John K Smith" when "John K Smith" is also on the same
side and would correctly disqualify the match against "John R
Smith". The indexer uses `consolidate=False` to preserve
partial-name recall.

## Cross-stack flow

```
rigour                    followthemoney             nomenklatura / yente
──────                    ──────────────             ────────────────────
analyze_names()    ←──    entity_names(entity)  ←──  matcher / indexer
pair_symbols()
pick_name()
Name / NamePart / Span / Symbol pyclasses (read-only at the consumer level
                                           except for tag mutation during
                                           the rigour-internal analyze pass)
```

The boundaries:

- **rigour** owns the name engine. No schema awareness, no
  matcher policy.
- **followthemoney** owns the entity-to-strings projection
  (`entity_names`). Reads schema-aware name properties, packages
  them into `analyze_names`'s positional args. No matcher policy.
- **nomenklatura / yente** own matcher and indexer policy.
  `nomenklatura/matching/logic_v2/names/match.py` is the canonical
  matcher consumer; yente flattens `Name` into ES fields for
  indexing.

## Open questions

### Symbol memory at scale

At ~100-200k unique IDs and millions of Symbol instances on the
matcher side, the `Arc<str>` interner is the primary
allocation. Two follow-ups remain on the table:

- **`compact_str`-style inline small strings.** Most IDs fit in
  ≤24 bytes. Saves the interner entirely but loses sharing for
  repeated long-ish IDs. Memory-wise within ~10% of interned Arc;
  simplicity-wise cleaner. Spike when memory matters.
- **Per-process Symbol registry.** Assign each distinct
  `(category, id)` a dense `u32` at first construction; `Symbol`
  collapses to one word. Big memory win at matching-index scale,
  more machinery. Possible end state.
- **Category-local interners.** One `RwLock<HashMap>` per
  category rather than a global one. Enables `Symbol::eq` as
  pure `Arc::ptr_eq` without content fallback. Defer until
  profiling shows the single global lock is a bottleneck.

### Splitting `NAME` into semantic sub-categories

Considered and rejected: the heterogeneous id model reflects real
source diversity (Wikidata, manual overrides, future schemes) and
the single bucket is the right place to absorb it. Revisit only
if downstream matching ever needs distinct weights per source.

### Matcher-side pruning

`names_product` (in nomenklatura's `logic_v2/names/analysis.py`)
prunes the cross product of two `Name` sets before the expensive
inner scoring loop. Gates: shared script via `common_scripts` on
`comparable`, plus a per-query symbol-overlap dominance pass.
Live design discussion: `plans/name-matcher-pruning.md`. Not part
of rigour proper but uses rigour primitives heavily.

### `analyze_names` API shape

Currently a kwargs function. An `#[pyclass] AnalyzeRequest`
shape would be more type-safe and extensible, especially as the
flag surface grows. Decided case-by-case if/when new flags
arrive.

### `pick_lang_name` Rust port

Stays Python — thin language-filter wrapper, not hot. Port only
if profiling justifies. Note: not currently in
`rigour.names.__all__`; should be added to surface it
consistently with the rest of the pick family.

### Per-script transliteration ordering in `analyze_names`

The pipeline for ORG/ENT is currently per-script-loop →
casefold → org-type-replace → ... For PER it's prefix strip →
casefold → ... If org-type aliases ever need to match
non-Latin source forms (e.g. Cyrillic "ООО"), the ordering
needs revisiting; today it works because the org-type alias
table includes both source-script and Latin forms.
