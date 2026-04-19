---
description: Replace rigour's normalizer-callback pattern with a flag-based normalize() function; policy for Python/Rust function duplication
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
   `normalize(text, flags)` function.

## Part 1 — duplication policy

**When to duplicate instead of FFI**:

- Function body is <~50ns of work.
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
and are single-sourced. The Normalizer work below is an example — one
Rust function, one Python wrapper, no Python parallel of the steps.

## Part 2 — normalizer flag model

### Catalog of observed normalizers

Grepped rigour for `normalize_*` functions and callsites taking
`normalizer: Normalizer`. Twelve functions, but they decompose to a
small set of primitive operations.

| Function | File | Steps |
|----------|------|-------|
| `normalize_text` | `rigour/text/stopwords.py` | casefold → category_replace(SLUG_CATEGORIES) → squash_spaces |
| `normalize_name` | `rigour/names/tokenize.py` | prenormalize (casefold) → tokenize → join |
| `normalize_display` | `rigour/names/org_types.py` | squash_spaces |
| `_normalize_compare` | `rigour/names/org_types.py` | squash_spaces → casefold |
| `normalize_address` | `rigour/addresses/normalize.py` | lower → category_replace → optional ascii → squash |
| `normalize_territory_name` | `rigour/territories/util.py` | NFKD → casefold → strip(SKIP_CHARACTERS) → category_replace → conditional latinize → NFKC → squash |
| `normalize_code` | `rigour/langs/util.py` | lower → strip |
| `normalize_unit` | `rigour/units.py` | lower → dict lookup |
| `normalize_extension` | `rigour/mime/filename.py` | strip dot → splitext → slugify |
| `normalize_mimetype` | `rigour/mime/mime.py` | delegate to MIME parser |
| `noop_normalizer` | `rigour/text/dictionary.py` | strip |
| `prenormalize_name` | `rigour/names/tokenize.py` | casefold |

### Observed primitive operations

1. **strip** — trim leading/trailing whitespace
2. **casefold** — Unicode casefolding (NOT lowercase; differs for ß → ss)
3. **lower** — ASCII-ish lowercase (rarely needed once casefold exists)
4. **NFC / NFKC / NFKD** — Unicode normal forms
5. **squash_spaces** — runs of whitespace → single space, trim
6. **category_replace** — Unicode category → replacement string
7. **tokenize_join** — split by Unicode category, rejoin with separator
8. **latinize** — script → Latin, preserving diacritics
9. **ascii** — full Latin → ASCII (implies latinize + NFKD + mark strip + fallback)
10. **conditional_latinize** — latinize only if `can_latinize(text)` (territory-specific; might drop, see below)

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

        // Unicode normalisation (mutually exclusive; leftmost set wins)
        const NFC           = 1 << 3;
        const NFKC          = 1 << 4;
        const NFKD          = 1 << 5;

        // Script conversion (ASCII implies LATINIZE at a lower level)
        const LATINIZE      = 1 << 6;
        const ASCII         = 1 << 7;

        // Token pass (splits by Unicode category, rejoins with space)
        const TOKENIZE      = 1 << 8;

        // Presets matching current rigour normalizers
        const FORM_BASIC    = Self::STRIP.bits() | Self::SQUASH_SPACES.bits();
        const FORM_COMPARE  = Self::FORM_BASIC.bits() | Self::CASEFOLD.bits();
        const FORM_NAME     = Self::CASEFOLD.bits() | Self::TOKENIZE.bits();
        const FORM_ASCII_COMPARE = Self::FORM_COMPARE.bits() | Self::ASCII.bits();
    }
}

pub fn normalize(text: &str, flags: Normalize) -> Option<String> {
    // Apply in a fixed order. Short-circuits to None on empty output.
}
```

**Fixed pipeline order** (independent of bit order):

1. STRIP (if set)
2. NFC / NFKC / NFKD (first-set-wins; should be mutex in practice)
3. CASEFOLD
4. ASCII, else LATINIZE (ASCII is a superset)
5. TOKENIZE (joins with " ", so it influences whitespace)
6. SQUASH_SPACES (last; collapses whatever whitespace earlier steps introduced)

Empty result → `None`, matching the existing contract on every
observed normalizer.

### Python exposure

```python
# rigour/text/normalize.py
from rigour._core import normalize as _normalize, Normalize

# Re-export the flag enum for Python callers.
__all__ = ["normalize", "Normalize"]

def normalize(text: Optional[str], flags: int) -> Optional[str]:
    if text is None:
        return None
    return _normalize(text, flags)
```

The `Normalize` enum crosses the FFI once, is cheap to pass thereafter
(it's just a u16).

### Mapping observed normalizers to flags

| Old function | New flag expression |
|--------------|---------------------|
| `normalize_text` | `FORM_COMPARE` + category_replace is **out of scope** (see below) |
| `normalize_name` | `FORM_NAME` (= CASEFOLD \| TOKENIZE) |
| `normalize_display` | `FORM_BASIC` (= STRIP \| SQUASH_SPACES) |
| `_normalize_compare` | `FORM_COMPARE` |
| `normalize_code` | `STRIP` — lower is mostly redundant given casefold, but `STRIP \| CASEFOLD` covers the ASCII case identically |
| `noop_normalizer` | `STRIP` |
| `prenormalize_name` | `CASEFOLD` |

**Not covered by the flag model** (intentionally):

- `normalize_text`'s `category_replace(SLUG_CATEGORIES)` — this is
  slug-specific and doesn't belong in a general normalizer. If stopwords
  really need it, either (a) subsume it into `TOKENIZE` (they're almost
  equivalent) or (b) add a `CATEGORY_SLUG` flag if we find it's truly
  distinct. Revisit during stopwords porting.
- `normalize_address`, `normalize_territory_name` — both layer
  domain-specific logic (custom character maps, conditional latinize gated
  by script detection, kitchen-sink category_replace) on top of the
  generic steps. These stay as their own functions; internally they'll
  call `normalize(text, flags)` with the generic bits and handle their
  own specifics.
- `normalize_unit`, `normalize_mimetype`, `normalize_extension` —
  domain-specific. Not part of the "normalizer callback" pattern; no
  change needed.

### Call sites that currently take a `normalizer` callback

These are the functions whose `normalizer: Normalizer` parameter becomes
`flags: Normalize` in the new API:

- `rigour/names/tagging.py`: `_get_org_tagger`, `_get_person_tagger`,
  `tag_org_name`, `tag_person_name`
- `rigour/text/stopwords.py`: `is_stopword`, `is_nullword`, `is_nullplace`
- `rigour/names/check.py`: `is_stopword`, `is_nullword`,
  `is_generic_person_name`
- `rigour/names/org_types.py`: `replace_org_types_compare`,
  `replace_org_types_display`, `remove_org_types`, `extract_org_types`
- `rigour/names/person.py`: `load_person_names_mapping`

For each, the signature becomes:

```python
def tag_org_name(name: Name, flags: Normalize = Normalize.FORM_NAME) -> Name: ...
```

Default flags match the current default normalizer in each case.

**API compatibility note**: tag/check/replace functions currently accept a
callable. Converting to flags is a breaking change. Options:

- **Break cleanly**: remove the callback argument, add `flags=` with a
  sensible default. Upgrade the downstream callers in nomenklatura/FTM in
  a coordinated commit.
- **Soft-deprecate**: add `flags=` as a new parameter, keep accepting
  `normalizer=` for one release but warn. Remove in the next.

Break cleanly. Rigour is pre-2.0; the API churn is acceptable and the
deprecation window adds complexity for no real adopter benefit.

### Rust wiring

```rust
// rust/src/text/normalize.rs (sketch)
pub fn normalize(text: &str, flags: Normalize) -> Option<String> {
    let mut s = if flags.contains(Normalize::STRIP) {
        text.trim().to_string()
    } else {
        text.to_string()
    };

    // Unicode normal form (at most one set)
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
        s = ascii_text(&s);  // via _core::transliterate::ascii_text
    } else if flags.contains(Normalize::LATINIZE) {
        s = latinize_text(&s);
    }

    if flags.contains(Normalize::TOKENIZE) {
        s = tokenize_join(&s, " ");
    }

    if flags.contains(Normalize::SQUASH_SPACES) {
        s = squash_spaces(&s);
    }

    if s.is_empty() { None } else { Some(s) }
}
```

Dependencies already in the crate:
- `icu::normalizer` — NFC/NFKC/NFKD
- ICU4X `Transliterator` — ASCII/LATINIZE (via existing
  `text::transliterate`)
- `unicode-general-category` + existing `tokenize_name` Rust parallel —
  TOKENIZE
- In-crate `squash_spaces` (trivial; no new dep)
- Rust's `char::to_lowercase` or `str::to_lowercase` approximates
  CASEFOLD. Full Unicode casefold is a separate ICU4X API; if the
  difference matters for ß and similar, use `icu::casemap::CaseMapper`.

**CASEFOLD implementation decision needed**: check ICU4X 2.x —
`icu::casemap::CaseMapper::fold()` is the right API if it's in
`compiled_data`. If not, Rust's stdlib `str::to_lowercase()` is a
partial substitute that disagrees on German ß and Turkish I/ı. Verify
before committing; parity with Python's `str.casefold()` matters for
stopword lookups.

### Python rigour surface

New module:

- `rigour/text/normalize.py` — re-exports `Normalize` flag + `normalize`
  function from `_core`.

Retired functions (breaking change, same PR):

- `rigour.text.stopwords.normalize_text`
- `rigour.names.tokenize.normalize_name` — replaced by
  `normalize(text, Normalize.FORM_NAME)`. The Python tokeniser stays
  (duplication policy!) but `normalize_name` itself disappears as a
  public symbol.
- `rigour.names.org_types.normalize_display`, `_normalize_compare`
- `rigour.text.dictionary.noop_normalizer`

Kept (they're domain-specific wrappers, not generic):

- `rigour.addresses.normalize.normalize_address`
- `rigour.territories.util.normalize_territory_name`
- `rigour.langs.util.normalize_code`
- `rigour.units.normalize_unit`
- `rigour.mime.*.normalize_*`

### Verification

- Unit tests in `rust/src/text/normalize.rs` covering each flag in
  isolation and the FORM_* presets against hand-picked inputs.
- Python tests in `tests/text/test_normalize.py` asserting that
  `normalize(text, FORM_X)` matches the current output of the
  corresponding legacy normalizer for a corpus of 50–100 representative
  inputs.
- All tagging/dictionary tests (`tests/names/test_tagging.py`,
  `tests/text/test_stopwords.py`, `tests/names/test_org_types.py`)
  continue to pass after flipping their call sites from `normalizer=`
  to `flags=`.

## Open questions

1. **CASEFOLD parity**: does ICU4X's `CaseMapper::fold()` match Python's
   `str.casefold()` exactly, including ß → ss and Turkish edges? Verify
   before shipping. Fallback: Rust's `to_lowercase()` + known-case
   overrides for the ~5 divergent characters.
2. **Is `category_replace(SLUG_CATEGORIES)` genuinely needed** in the
   flag set, or does `TOKENIZE` cover the same ground for our
   stopwords/dictionary callers? Inspect `SLUG_CATEGORIES` vs our tokenize
   classifier. Probably subsumed.
3. **Flag naming**: `Normalize::TOKENIZE` implies space-join. If any
   caller needs a different separator, expose `tokenize_with(sep)` as a
   separate function rather than making the separator part of the flag
   API. Keep flags simple.
4. **Thread-safety**: `normalize()` internally uses `ascii_text` and
   `latinize_text` which use thread-local ICU4X transliterator caches.
   `normalize()` is safe to call from any thread; each thread amortises
   its own lazy init.
