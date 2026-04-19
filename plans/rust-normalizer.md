---
description: Replace rigour's normalizer-callback pattern with a flag-based normalize() + named CategoryProfile; policy for Python/Rust function duplication
date: 2026-04-19
tags: [rigour, rust, normalization, api-design, names]
---

# rigour Rust port: normalization

Two related concerns from the names-system work:

1. **Duplication policy.** Some Python functions are so cheap that the
   PyO3/FFI crossing costs more than the function itself. For those, we
   duplicate: keep the Python implementation AND port an identical Rust
   version, share tests across both, make a single owner responsible for
   parity. Don't push to make every small Python helper an FFI call.

2. **Normalizer callback replacement.** Rigour's tagger and dictionary
   functions accept a `normalizer: Optional[str] -> Optional[str]`
   callback. That's untenable across the Rust boundary — calling a Python
   callback from Rust for every token is exactly the kind of fine-grained
   FFI that tanked the `fafo-rust` experiment. Replace with a flag-based
   `normalize(text, flags, categories)` function. **No preset
   compositions** — each caller defines its own flag combination inline.

## Part 1 — duplication policy

**When to duplicate instead of FFI**:

- Function body is <~50 ns of work.
- Called in a tight loop where each call is per-token, not per-string.
- No data dependencies that would force a data-synchronisation story.
- Has a small, well-pinned test corpus.

**Example — `tokenize_name`.** Pure-Python tokenisation walks characters,
classifies by Unicode category, emits tokens. Per-call cost is
microseconds but per-character work is nanoseconds. Porting to Rust
amortises if called on big strings, but rigour calls it on single tokens
(5–50 chars). FFI overhead > saved compute. Ship a Rust version for the
Rust-side callers (inside the tagger, inside `analyze_names`), keep the
Python version for the Python-side callers, share a test corpus between
them.

**When NOT to duplicate**:

- Any data-heavy function (Aho-Corasick taggers, transliterators,
  distance computations on anything longer than a few chars). These
  actually win from being Rust — FFI amortises.
- Anything with substantial state (regex compilation, lazy
  initialisation). The state should be owned by one side; the other side
  should delegate.

**Contract for shared-behaviour duplicates**:

- Test corpus is the source of truth. Same input table exercised by
  both implementations.
- CI has separate steps running the Python test and the Rust test
  (`cargo test`) against that corpus.
- Any output divergence is a test failure. Fix by bringing one
  implementation in line with the other; don't pin divergent expected
  values.
- Documentation on both sides cross-references: "Rust parallel at
  `rust/src/text/tokenize.rs`" and "Python parallel at
  `rigour/names/tokenize.py`".

**Not covered by this policy**: functions that go through `rigour._core`
and are single-sourced. The normalizer work below is an example — one
Rust function, one Python wrapper, no Python parallel of the steps.

## Part 2 — normalizer flag model

### Design decisions

- **No FORM_* presets.** Callers (org_types, stopwords, tagging, …)
  define their own flag composition inline and name it locally if they
  want. The module exposes `normalize()` + `Normalize` flags + a tiny
  `CategoryProfile` enum, nothing else.
- **No TOKENIZE flag.** Tokenisation is a separate concern with its own
  return type (`List[str]`, not `Optional[str]`) and lives in
  `rigour.names.tokenize`. It is not a normalization step.
- **`category_replace` is in scope** as a normalization step — it's what
  most of rigour's existing normalizers use to collapse punctuation /
  symbols / controls. Instead of exposing the full category-map as a
  parameter (as normality does), expose a closed `Cleanup` enum with
  three variants — `Noop`, `Strong`, `Slug`. Default is `Cleanup::Noop`
  (no category replacement).
- **Reference design**: `normality.normalize()`
  (`/Users/pudo/Code/normality/normality/__init__.py`) is the existing
  "kitchen sink" normalizer. Our rigour version is a leaner version of
  that — no `stringify`/encoding concerns, no `replace_categories: Categories`
  free parameter, just the fixed `Cleanup` variants.

### Catalog of observed normalizers

Grepped rigour for `normalize_*` functions and callsites taking
`normalizer: Normalizer`. Twelve functions; nine decompose into the
primitives below, three are domain-specific wrappers that stay as-is.

| Function | File | Steps |
|----------|------|-------|
| `normalize_text` | `rigour/text/stopwords.py` | casefold → category_replace(SLUG) → squash_spaces |
| `normalize_name` | `rigour/names/tokenize.py` | casefold → tokenize → join  (tokenize is not part of the flag system; this becomes a `normalize(..., NAME) + tokenize_name()` composition on the Python side) |
| `normalize_display` | `rigour/names/org_types.py` | squash_spaces |
| `_normalize_compare` | `rigour/names/org_types.py` | squash_spaces → casefold |
| `normalize_address` | `rigour/addresses/normalize.py` | lower → category_replace(custom) → optional ascii → squash |
| `normalize_territory_name` | `rigour/territories/util.py` | NFKD → casefold → strip(SKIP_CHARACTERS) → category_replace → conditional latinize → NFKC → squash |
| `normalize_code` | `rigour/langs/util.py` | lower → strip |
| `normalize_unit` | `rigour/units.py` | lower → dict lookup |
| `normalize_extension` | `rigour/mime/filename.py` | strip dot → splitext → slugify |
| `normalize_mimetype` | `rigour/mime/mime.py` | delegate to MIME parser |
| `noop_normalizer` | `rigour/text/dictionary.py` | strip |
| `prenormalize_name` | `rigour/names/tokenize.py` | casefold |

### Primitive operations

1. **strip** — trim leading/trailing whitespace
2. **casefold** — Unicode casefolding (NOT lowercase; differs for ß → ss)
3. **NFC / NFKC / NFKD** — Unicode normal forms
4. **category_replace** — Unicode category → WS / delete / keep, driven by one of three fixed profiles (see below)
5. **latinize** — script → Latin, preserving diacritics
6. **ascii** — full Latin → ASCII (implies latinize + NFKD + mark strip + fallback)
7. **squash_spaces** — runs of whitespace → single space, trim

No `tokenize` (separate concern, separate return type). No `lower` (casefold supersedes it in all rigour callers we looked at; lossless for ASCII and more correct for ß/Turkish I).

### Cleanup variants

Three variants, all represented explicitly on the enum. `Noop` is the
default.

| Variant | Source | Intent |
|---------|--------|--------|
| `Noop` | — | Skip category replacement entirely. The default. |
| `Strong` | `normality.constants.UNICODE_CATEGORIES` | Aggressive text cleanup — punctuation/symbols/controls → WS, marks (except Mc) deleted. The "kitchen-sink" profile for matching keys. |
| `Slug` | `normality.constants.SLUG_CATEGORIES` | URL-slug-style cleanup — similar to Strong but keeps Lm (modifier letters) and Mn (nonspacing marks). Used by stopwords today; also the intended input for the future `slugify` port. |

Cleanup variants are **fixed** in Rust. Callers cannot pass a custom
category map; the only options are the three above. Adding another
variant is a trivial change when a new use case appears.

**Why no `Name` variant yet**: an earlier draft proposed a `Name`
profile ported from `rigour.names.tokenize.TOKEN_SEP_CATEGORIES` +
`SKIP_CHARACTERS` + `KEEP_CHARACTERS`. Deferred until the tokenizer
port happens — the category-map used by `tokenize_name` is tangled with
tokenization semantics (separator vs. delete vs. keep for each
category) and is better thought of as an internal detail of the
tokenizer rather than a standalone normalizer mode. Revisit then.

**Why `Slug` now**: it's cheap to land alongside `Strong` (same table
shape, trivial port from `normality.constants.SLUG_CATEGORIES`), and
the slugify port is on the roadmap. Shipping the variant now means the
eventual slugify implementation is a pure consumer of the normalizer
API, not a dependency change.

### Flag model

```rust
// rust/src/text/normalize.rs
use bitflags::bitflags;

bitflags! {
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Normalize: u16 {
        // Whitespace / edges
        const STRIP         = 1 << 0;
        const SQUASH_SPACES = 1 << 1;

        // Case
        const CASEFOLD      = 1 << 2;

        // Unicode normalisation (at most one meaningfully set; later
        // forms win if multiple)
        const NFC           = 1 << 3;
        const NFKC          = 1 << 4;
        const NFKD          = 1 << 5;

        // Script conversion (ASCII implies LATIN at a lower level)
        const LATIN      = 1 << 6;
        const ASCII         = 1 << 7;
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Cleanup {
    #[default]
    Noop,    // skip category replacement
    Strong,  // ≈ normality.UNICODE_CATEGORIES
    Slug,    // ≈ normality.SLUG_CATEGORIES
}

pub fn normalize(
    text: &str,
    flags: Normalize,
    cleanup: Cleanup,
) -> Option<String> {
    // Fixed pipeline order; see below. `Cleanup::Noop` skips the
    // category-replace step entirely.
}
```

**Fixed pipeline order** (independent of bit order; matches
`normality.normalize` ordering):

1. STRIP (if set)
2. NFC / NFKC / NFKD (first-set-wins, or apply in declaration order if
   multiple somehow set — shouldn't happen in practice)
3. CASEFOLD
4. ASCII, else LATIN (ASCII is a superset — running ASCII subsumes
   LATIN if both are set)
5. category_replace (if `cleanup != Cleanup::Noop`)
6. SQUASH_SPACES

Empty result → `None`, matching the existing contract on every observed
normalizer.

### Python exposure

```python
# rigour/text/normalize.py
from rigour._core import normalize as _normalize
from rigour._core import Normalize, Cleanup

__all__ = ["normalize", "Normalize", "Cleanup"]

def normalize(
    text: Optional[str],
    flags: Normalize,
    cleanup: Cleanup = Cleanup.Noop,
) -> Optional[str]:
    if text is None:
        return None
    return _normalize(text, flags, cleanup)
```

The `Normalize` flag value and `Cleanup` enum cross the FFI boundary as
small ints, ~zero marshalling cost. `Cleanup.Noop` (the default) skips
category replacement entirely.

### Callers define their own compositions

Each caller expresses its normalizer inline. No FORM_* presets exposed
from the module. Examples of what current call sites become:

```python
# rigour/names/org_types.py — replacing normalize_display
#   (was: squash_spaces)
from rigour.text.normalize import normalize, Normalize

def _display(text):
    return normalize(text, Normalize.STRIP | Normalize.SQUASH_SPACES)

# replacing _normalize_compare (was: squash_spaces + casefold)
def _compare(text):
    return normalize(
        text,
        Normalize.STRIP | Normalize.CASEFOLD | Normalize.SQUASH_SPACES,
    )
```

```python
# rigour/text/stopwords.py — replacing normalize_text
#   (was: casefold + category_replace(SLUG) + squash_spaces).
#   The stopwords path is actually the only current rigour caller using
#   the SLUG profile. If a future grep shows nothing else will use Slug,
#   consider promoting this to Cleanup.Strong — the stopword corpus
#   doesn't care about Lm/Mn. For now, preserve current behaviour.
from rigour.text.normalize import normalize, Normalize, Cleanup

def _stopword_key(text):
    return normalize(
        text,
        Normalize.CASEFOLD | Normalize.SQUASH_SPACES,
        Cleanup.Slug,
    )
```

```python
# rigour/names/tagging.py — tag_org_name / tag_person_name
#   The old normalizer was normalize_name (casefold + tokenize + join).
#   Tokenisation is a separate concern (rigour.names.tokenize.tokenize_name)
#   and tokenize_name's internal category handling is not exposed as a
#   Cleanup variant — that's tangled with tokenizer semantics and will be
#   revisited when the tokenizer ports over.
#
#   Until then, the tagger calls tokenize_name directly on pre-normalized
#   input, rather than round-tripping through the flag-based normalizer:
from rigour.text.normalize import normalize, Normalize
from rigour.names.tokenize import tokenize_name

def _name_tokens(text):
    # Casefold via normalize, then tokenize. No Cleanup pass — the
    # tokenizer already handles category-based separation internally.
    folded = normalize(text, Normalize.CASEFOLD)
    return tokenize_name(folded) if folded else []
```

The callback-taking functions (`tag_org_name`, `is_stopword`, etc.)
**keep** their parameterisation — they still let the caller choose how
the function's internal reference data (org-type aliases, stopword
list, AC patterns) is normalised when the regex or automaton is built.
What changes is the shape of that parameter: the old
`normalizer: Callable[[Optional[str]], Optional[str]]` becomes
`normalize_flags: Normalize` (plus optional `cleanup: Cleanup` when
the normaliser needs a category-replace step). Semantics are preserved:
the caller is expected to normalise its runtime input with the **same**
flag set before calling, exactly as it does today via the passed-in
callback. See the next subsection for the full shape of the pattern.

### Reference-data normalisation: keep the override, as flags

There are **two** places where `Normalize` flags get used, and they
have different lifecycles. The earlier parts of this document cover the
first; this subsection describes the second and is the bridge to
understanding what happens to callback-taking functions like
`replace_org_types_compare` and `is_stopword`.

| Use | Who calls `normalize()` | What's normalised | When |
|---|---|---|---|
| **Input normalisation** | The caller, *before* handing text to a lookup/tagger function | A single runtime string | On every call |
| **Reference-data normalisation** | The lookup/tagger function *itself*, during regex/automaton construction | The static alias list / stopword list / AC pattern set | Once per distinct flag set (cached) |

Same `normalize()` implementation, same flag vocabulary — different
lifecycle and different owner. The reference-data path is where the
old `normalizer=` callback lives. Dropping it entirely (as an earlier
draft of this plan suggested) would have thrown away the ability for
callers to choose how aliases get built into the internal structures
— which nomenklatura, yente, and FTM all currently rely on via
`normalizer=prenormalize_name`. We keep that override, just express it
as flags.

**Functions in the reference-data bucket** (all keep a parameterised
entry point after the port):

- `rigour/names/org_types.py`: `replace_org_types_compare`,
  `replace_org_types_display`, `remove_org_types`, `extract_org_types`
- `rigour/names/tagging.py`: `tag_org_name`, `tag_person_name`
- `rigour/text/stopwords.py`, `rigour/names/check.py`: `is_stopword`,
  `is_nullword`, `is_nullplace`, `is_generic_person_name`
- `rigour/names/person_names.py`: `load_person_names_mapping`

**New API shape** (representative — the other functions follow the
same pattern):

```python
# rigour/names/org_types.py
def replace_org_types_compare(
    name: str,
    normalize_flags: Normalize = Normalize.CASEFOLD,
    cleanup: Cleanup = Cleanup.Noop,
    generic: bool = False,
) -> str:
    ...
```

The default flag value matches what nomenklatura, yente, and FTM pass
in practice today (casefold only, via `prenormalize_name`) — **not**
the old Python default `_normalize_compare` (squash + casefold). This
is a deliberate default change: production callers already override,
so aligning the default with production means the common path needs
zero caller-side changes. The old default was convenient for REPL use
and not much else.

**Caching.** Each distinct `(normalize_flags, cleanup)` combination
constructs a different Aho-Corasick automaton. The Rust side caches
them in a flag-keyed map, conceptually:

```rust
static REPLACERS: LazyLock<RwLock<HashMap<(Normalize, Cleanup), Arc<Replacer>>>> = ...;
```

First call with a given flag combo pays the build cost (~77 ms for
`replace_org_types_compare` measured via `benchmarks/bench_org_types.py`
— includes Python startup, JSON parse, AC build); subsequent calls
hit the cache. Empirically there are 1–2 distinct flag sets in use
across the rigour/FTM/nomenklatura/yente stack, so the cache size is
tiny and bounded by that in practice. This is the same lifecycle as
today's `@cache`-decorated `_compare_replacer` — we're preserving it,
not adding something new.

This cache is **not** the Phase-5 LRU scaffolding we're removing
elsewhere — that LRU caches match *results* keyed by input string. The
per-flag cache here keys compiled *patterns* and has a different shape,
size bound, and motivation.

### Mapping observed normalizers to compositions

The table below shows how each callback-based normaliser maps to a
`Normalize` flag composition. Two readings: (a) these are the **default
flag sets** each reference-data function will use internally when the
caller doesn't override, and (b) these are the flag sets the caller
should use when normalising its runtime input to match the function's
internal reference data.

| Old function | New composition |
|--------------|-----------------|
| `normalize_text` | `CASEFOLD \| SQUASH_SPACES` + `Cleanup.Slug` |
| `normalize_name` | `CASEFOLD`, then `tokenize_name()` if tokens are wanted. No `Cleanup` pass — tokenizer handles category separation internally. Revisit when the tokenizer ports over. |
| `normalize_display` | `STRIP \| SQUASH_SPACES` (no cleanup) |
| `_normalize_compare` | `STRIP \| CASEFOLD \| SQUASH_SPACES` (no cleanup) |
| `normalize_code` | `STRIP \| CASEFOLD` (no cleanup) |
| `noop_normalizer` | `STRIP` (no cleanup) |
| `prenormalize_name` | `CASEFOLD` (no cleanup) |

**Not covered by the flag model** (intentionally):

- `normalize_address`, `normalize_territory_name` — both layer
  domain-specific logic (custom character maps, conditional latinize
  gated by script detection, address-specific category variants) on top
  of the generic steps. These stay as their own functions; internally
  they'll call `normalize(text, flags, categories)` with the generic
  bits and handle their own specifics.
- `normalize_unit`, `normalize_mimetype`, `normalize_extension` —
  domain-specific. Not part of the "normalizer callback" pattern; no
  change needed.

### Call sites that currently take a `normalizer` callback

These are the functions whose `normalizer: Normalizer` parameter swaps
out — the parameter stays, its type changes from
`Callable[[Optional[str]], Optional[str]]` to `Normalize` (plus
optional `Cleanup` where the old callback included a category-replace
step). See the "Reference-data normalisation" subsection above for the
full design:

- `rigour/names/tagging.py`: `_get_org_tagger`, `_get_person_tagger`,
  `tag_org_name`, `tag_person_name`
- `rigour/text/stopwords.py`: `is_stopword`, `is_nullword`, `is_nullplace`
- `rigour/names/check.py`: `is_stopword`, `is_nullword`,
  `is_generic_person_name`
- `rigour/names/org_types.py`: `replace_org_types_compare`,
  `replace_org_types_display`, `remove_org_types`, `extract_org_types`
- `rigour/names/person_names.py`: `load_person_names_mapping`

The signature shape changes (callable → flags), but the role of the
parameter is unchanged: it configures how the function's internal
reference data is normalised when the regex / automaton is built.
Callers that were passing `normalizer=prenormalize_name` today should
pass `normalize_flags=Normalize.CASEFOLD` post-port; callers relying on
the Python default `_normalize_compare` should pass
`normalize_flags=Normalize.CASEFOLD | Normalize.SQUASH_SPACES`. This is
still a breaking API change (callable-shaped → int-shaped argument);
given rigour is pre-2.0 and the consumers are small (ourselves +
nomenklatura + FTM), break cleanly in one PR rather than doing a
deprecation dance.

### Rust wiring

```rust
// rust/src/text/normalize.rs (sketch)
pub fn normalize(
    text: &str,
    flags: Normalize,
    cleanup: Cleanup,
) -> Option<String> {
    let mut s = if flags.contains(Normalize::STRIP) {
        text.trim().to_string()
    } else {
        text.to_string()
    };

    // Unicode normal form (at most one is meaningful)
    if flags.contains(Normalize::NFKD) {
        s = nfkd(&s);
    } else if flags.contains(Normalize::NFKC) {
        s = nfkc(&s);
    } else if flags.contains(Normalize::NFC) {
        s = nfc(&s);
    }

    if flags.contains(Normalize::CASEFOLD) {
        s = casefold(&s);
    }

    if flags.contains(Normalize::ASCII) {
        s = ascii_text(&s);              // existing text::transliterate
    } else if flags.contains(Normalize::LATIN) {
        s = latinize_text(&s);           // existing text::transliterate
    }

    if cleanup != Cleanup::Noop {
        s = category_replace(&s, cleanup);
    }

    if flags.contains(Normalize::SQUASH_SPACES) {
        s = squash_spaces(&s);
    }

    if s.is_empty() { None } else { Some(s) }
}

fn category_replace(text: &str, cleanup: Cleanup) -> String {
    // Fixed tables: one match arm per Cleanup variant (Noop handled by
    // the caller via the early return). Each variant's table is a const
    // array populated from the ported UNICODE_CATEGORIES (Strong) /
    // SLUG_CATEGORIES (Slug) data.
}
```

Dependencies already in the crate:
- `icu::normalizer` — NFC/NFKC/NFKD
- ICU4X `Transliterator` — ASCII/LATIN (via existing
  `text::transliterate`)
- In-crate `category_replace` using `unicode-general-category` to map
  each char to its category and a per-profile table to resolve the
  action
- In-crate `squash_spaces` (trivial; no new dep)
- CASEFOLD: check `icu::casemap::CaseMapper::fold()` first; fall back to
  a hand-rolled table if `compiled_data` doesn't include it

**CASEFOLD implementation decision needed**: verify that ICU4X's
`CaseMapper::fold()` gives the same output as Python's `str.casefold()`
for the cases that matter in rigour (ß → ss, Turkish I/ı dotless,
Greek sigma forms). If `compiled_data` doesn't carry the casemap, use
Rust's `str::to_lowercase()` + known overrides for the ~5 divergent
characters.

### Python rigour surface

New module:

- `rigour/text/normalize.py` — re-exports `normalize`, `Normalize`, and
  `CategoryProfile`.

Retired functions (eventual breaking change, done in a scoped migration
PR later):

- `rigour.text.stopwords.normalize_text`
- `rigour.names.tokenize.normalize_name` — replaced by an inline
  composition in callers. `rigour.names.tokenize.tokenize_name` stays
  (it's the token-producing function, separate concern).
- `rigour.names.tokenize.prenormalize_name` — trivially `text.casefold()`.
  Retires with the `normalize_name` migration.
- `rigour.names.org_types.normalize_display`, `_normalize_compare`
- `rigour.text.dictionary.noop_normalizer` — strip-and-None-on-empty
  Normalizer. Retires when the `Normalizer` callback pattern is fully
  replaced by `flags=`. **Do not route through the Rust `normalize()`
  just to strip** — the FFI cost is larger than `str.strip()`.
- `Normalizer` type alias in `rigour.text.dictionary` — kept for now;
  retires when the callback pattern is fully replaced by `flags=`.

Already done (April 2026) — minor hygiene fixes that live outside the
callback-migration story:

- **`str.casefold()` in place of `str.lower()`** in
  `rigour.langs.util.normalize_code` and
  `rigour.addresses.normalize.normalize_address`. `str.lower()`
  mishandles ß, Turkish dotted-I, and Greek sigma forms; `str.casefold()`
  is the correct operation for case-insensitive equality. Output
  differs on non-ASCII inputs with these characters; ASCII-only inputs
  are unchanged.

Kept (domain-specific wrappers, not generic):

- `rigour.addresses.normalize.normalize_address`
- `rigour.territories.util.normalize_territory_name`
- `rigour.langs.util.normalize_code`
- `rigour.units.normalize_unit`
- `rigour.mime.*.normalize_*`

### Verification

- Unit tests in `rust/src/text/normalize.rs` covering each flag in
  isolation, each `CategoryProfile`, and a few representative
  compositions against hand-picked inputs.
- Python tests in `tests/text/test_normalize.py` asserting that
  `normalize(text, flags, categories)` matches the current output of
  the corresponding legacy normalizer for a corpus of 50–100
  representative inputs (one parity block per retired function).
- All tagging/dictionary tests (`tests/names/test_tagging.py`,
  `tests/text/test_stopwords.py`, `tests/names/test_org_types.py`)
  continue to pass after flipping their call sites from `normalizer=`
  to inline normalization.

### Cleanup data — sourcing

Both variants copy their category → action tables from existing Python
sources:

- `Strong` — verbatim from `normality.constants.UNICODE_CATEGORIES`
- `Slug` — verbatim from `normality.constants.SLUG_CATEGORIES`

These are small tables (~25 entries each) — generate as const arrays
in `rust/src/text/normalize.rs` at port time; no genscripts step needed.

The `Name`-profile data (`TOKEN_SEP_CATEGORIES` + `SKIP_CHARACTERS` +
`KEEP_CHARACTERS` from `rigour.names.tokenize`) stays internal to the
tokenizer for now. If the tokenizer port later proves that a
standalone `Cleanup::Name` variant would be useful, add it then.

## Open questions

1. **CASEFOLD parity**: does ICU4X's `CaseMapper::fold()` match Python's
   `str.casefold()` exactly, including ß → ss and Turkish edges? Verify
   before shipping. Fallback: Rust's `to_lowercase()` + known-case
   overrides for the ~5 divergent characters.
2. **Thread-safety**: `normalize()` internally uses `ascii_text` and
   `latinize_text` which use thread-local ICU4X transliterator caches.
   `normalize()` is safe to call from any thread; each thread amortises
   its own lazy init.
3. **Will stopwords stay on `Slug`, or promote to `Strong`?** Stopwords
   is the only current rigour consumer of `Cleanup.Slug`. The slug
   profile was designed for URL slugs (normality); its distinguishing
   trait is preserving Lm/Mn, which stopword keys don't obviously
   need. Keep on `Slug` for parity with current behaviour, revisit if
   we can prove `Strong` produces identical stopword keys in practice.
   Not blocking — trivial to flip once decided.
