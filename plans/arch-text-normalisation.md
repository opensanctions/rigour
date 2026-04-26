---
description: Architecture of rigour's text-normalisation primitives — the Normalize/Cleanup flag set, tokenize_name, maybe_ascii/should_ascii, common_scripts, and the deliberate scope cap on transliteration.
date: 2026-04-26
tags: [rigour, text, normalize, transliteration, icu4x, scripts, architecture]
---

# Text normalisation: architecture

This document covers rigour's text-level primitives: the
flag-based `normalize()` pipeline, tokenisation, transliteration,
and script detection. For the broader Rust core conventions see
`arch-rust-core.md`. For how the name pipeline composes these
primitives see `arch-name-pipeline.md`.

## The three primitives

`rigour.text.normalize` exposes:

- **`Normalize`** — a bit-flag set selecting individual
  normalisation steps.
- **`Cleanup`** — an enum picking one of two fixed
  Unicode-category replacement profiles (`Strong`, `Slug`), or
  `Noop`.
- **`normalize(text, flags, cleanup)`** — the single entry point
  running the composed pipeline.

Plus two utility types lifted alongside:

- **`Normalizer`** — the type alias `Callable[[Optional[str]],
  Optional[str]]`. Used by parametric predicates
  (`is_stopword`, `is_nullword`, `is_nullplace`,
  `is_generic_person_name`) so callers can supply whatever
  normalisation shape they need.
- **`noop_normalizer`** — the identity normaliser that strips
  whitespace and rejects empty input. Default `Normalizer` for
  callers whose input is already in the desired shape.

`Normalizer` and `noop_normalizer` live in
`rigour.text.normalize` for semantic adjacency to the rest of the
normalisation surface.

## Pipeline order

Steps run in a fixed order regardless of bit-ordering in the flag
value:

1. **STRIP** — trim leading/trailing whitespace.
2. **NFKD / NFKC / NFC** — at most one is meaningful; if multiple
   are set, Rust applies the first one its dispatch finds (NFKD).
3. **CASEFOLD** — Unicode full casefold (e.g. `ß → ss`). Not the
   same as `str.lower()` — casefold is the correct tool for
   case-insensitive comparison across Unicode.
4. **Cleanup** — `category_replace` driven by the chosen variant
   (`Strong` or `Slug`). Skipped when `Cleanup.Noop`.
5. **SQUASH_SPACES** — collapse whitespace runs and trim edges.
   Runs after step 4 so it can clean up whitespace that
   `category_replace` might have introduced.
6. **NAME** — run `tokenize_name` and rejoin tokens with a single
   ASCII space. Subsumes squashing. Implements the legacy
   `normalize_name` composition.

Empty output coalesces to `None`, matching the contract of the
pre-flags `Optional[str]` normalisers.

### Common compositions

These are the flag sets in use across the OpenSanctions stack;
the defaults on `replace_org_types_compare` and friends are
pinned to them.

- **`Normalize.CASEFOLD`** — production default for comparison
  keys that should preserve whitespace and script.
- **`Normalize.CASEFOLD | Normalize.SQUASH_SPACES`** — adds
  whitespace collapsing on top. Used by display-style replacers
  and stopword keys.
- **`Normalize.SQUASH_SPACES`** — whitespace-tidy without case
  change. Used by display-form replacers that preserve caller
  case.
- **`Normalize.CASEFOLD | Normalize.NAME`** — casefold and
  tokenise, yielding a stable space-separated key. The
  drop-in replacement for the legacy `normalize_name`.

### Two distinct uses of the flag set

The same `Normalize` vocabulary shows up in two places with
different lifecycles:

1. **Input normalisation.** A caller runs `normalize(text,
   flags, cleanup)` on a runtime string. This is what the public
   function does directly.
2. **Reference-data normalisation.** A lookup function (the
   org-type replacer, the AC tagger, …) builds an internal
   regex/automaton from static data and uses the flag set to
   decide how that static data normalises at build time. The
   caller is expected to normalise its runtime input with the
   *same* flags before calling. Functions in this bucket cache
   one compiled automaton per distinct `(flags, cleanup)`
   combination, process-wide in a `RwLock<HashMap>` on the Rust
   side. Empirically 1-2 distinct combos across the whole stack.

## `tokenize_name`

Rust-backed via `rigour._core.tokenize_name`; Python wrapper at
`rigour/names/tokenize.py`. Implementation in
`rust/src/text/tokenize.rs`.

Splits a name into tokens using Unicode general-category as the
separator rule:

- **Whitespace (separator)**: Cc, Zs, Zl, Zp, Pc, Pd, Ps, Pe,
  Pi, Pf, Po, Sm, So.
- **Delete**: Cf, Co, Cn, Lm (with KEEP_CHARS exceptions), Mn,
  Me, No, Sc, Sk.
- **Keep**: everything else (L\*, Nd, Nl, Mc).

Two override sets:

- **`SKIP_CHARS`** — always deleted, even when their general
  category would otherwise map to whitespace. Punctuation that
  should disappear inside words: `.`, ASCII apostrophe, curly
  quotation marks, modifier letter apostrophe / prime, grave and
  acute accents. So `"U.S.A."` → `["USA"]`, `"O'Brien"` →
  `["OBrien"]`.
- **`KEEP_CHARS`** — Lm characters that carry meaning in real
  CJK names: `ー` (KATAKANA-HIRAGANA PROLONGED SOUND MARK),
  `ｰ` (its halfwidth variant), `々` (IDEOGRAPHIC ITERATION
  MARK).

Mc (spacing combining marks) are kept because they are vowel
signs in Brahmic / Indic scripts (Myanmar, Devanagari, Tamil,
Thai) and essential parts of syllables. No Mc characters exist
in Latin / Cyrillic / Greek / CJK / Arabic ranges, so the
Latin-side cost is zero.

### `normalize_name`

`rigour.names.tokenize.normalize_name` is **deprecated**. Emits
`DeprecationWarning` on every call. Composes
`tokenize_name(casefold(name))` with a Python `@lru_cache`. The
implementation moved to a private `_normalize_name` so the
warning fires every call rather than once per cached input.

Replacements depend on caller intent:

- For "casefold + tokenise + space-join":
  `normalize(text, Normalize.CASEFOLD | Normalize.NAME)`.
- For ad-hoc composition: call `tokenize_name` and `casefold`
  directly.

## `maybe_ascii` and `should_ascii`

Rigour's only public transliteration surface, in
`rigour.text.translit` (Python wrapper) and
`rust/src/text/translit.rs` (Rust).

```python
def should_ascii(text: str) -> bool: ...
def maybe_ascii(text: str, drop: bool = False) -> str: ...
```

`should_ascii` is true iff every distinguishing script in `text`
is in `LATINIZE_SCRIPTS`. Pure-punctuation / pure-digit / empty
inputs return true vacuously (`text_scripts` filters
Common/Inherited).

`maybe_ascii` runs the four-stage pipeline:

1. **Per-script transliterators** (Cyrillic/Greek/Armenian/
   Georgian/Hangul → Latin). Latin input skips this step. Each
   non-Latin script in the input gets one ICU4X transliterator
   pass via the BCP-47-T locale `und-Latn-t-und-{script}`.
2. **NFKD + nonspacing-mark strip.** Decomposes base+combiner
   sequences (`é → e`); resolves compatibility variants
   (modifier letter `ʱ → ɦ`, superscript `ᵋ → ɛ`) so the next
   stage can act on the simplified base.
3. **CLDR Latin-ASCII transliterator** (`und-t-und-latn-d0-ascii`,
   baked into `icu_experimental_data`). Handles Latin Extended
   letters: `ĸ → q`, `ĳ → ij`, `ƙ → k`, `ɓ → b`, plus the
   Africanist surface broadly.
4. **`ASCII_FALLBACK`** — rigour's opinionated overrides for
   what CLDR deliberately leaves intact. Azerbaijani schwa
   `Ə → A`, African uppercase IPA letters `Ʒ → Z`, `Ɔ → O`,
   medievalist letters `Ȝ → Y`, Khoisan clicks dropped, glottal
   stops dropped, Catalan middle-dot stripped post-NFKD so
   `Ŀ`/`ŀ` geminate markers don't leak through.

Ordering matters: NFKD before Latin-ASCII lets CLDR's rules act
on the decomposed base letters rather than being stopped by
compatibility wrappers.

If any script in the input is outside `LATINIZE_SCRIPTS`, the
function returns the input unchanged (`drop=False`, default) or
the empty string (`drop=True`). The ASCII fast-path bypasses the
ICU4X pipeline entirely for ASCII input.

### `LATINIZE_SCRIPTS`

`{Latin, Cyrillic, Greek, Armenian, Georgian, Hangul}`. Six
scripts whose romanisation is well-defined enough for matching
purposes. The exact set lives in
`rigour.text.scripts.LATINIZE_SCRIPTS` and mirrors a constant in
`rust/src/text/translit.rs`.

Hangul is included; Han, Hiragana, Katakana are not. The
distinction is that Korean Hangul has unambiguous Revised
Romanization, while CJK Han is language-ambiguous (Japanese
kanji and Chinese ideographs share codepoints, ICU4X defaults to
Pinyin for both).

### Round-trip CI guard

`tests/text/test_translit.py::test_maybe_ascii_latin_roundtrip`
(Rust-side equivalent in `rust/src/text/translit.rs`)
enumerates every codepoint in the core Latin blocks (Latin-1
Supplement, Latin Extended-A/B, Latin Extended Additional, Latin
Ligatures) and asserts `maybe_ascii(c)` returns pure ASCII. Any
failure names the offending codepoint in the panic — forces a
deliberate decision when new Unicode adds a Latin Extended
letter that neither CLDR nor `ASCII_FALLBACK` handles.

Blocks outside the core range — IPA Extensions, Phonetic
Extensions, Latin Extended-C/D/E/F, Letterlike Symbols — are
explicitly out of scope. Their letters don't appear in real
name data, and downstream consumers that require ASCII
(`metaphone`, `soundex`) guard directly against non-ASCII input.

### Internal Rust callers and the in-Rust cache

Rust-internal callers of transliteration (the tagger's alias
build path, `pick_name`, `analyze_names`) don't go through the
Python `@lru_cache` wrapper. To avoid paying the full ICU4X cost
on every internal call, the relevant Rust function carries a
thread-local cap-N HashMap cache. Same shape as the Python LRU
but inside Rust — a deliberate exception to the
"caches-at-the-Python-boundary" rule, justified by the
nested-call pattern.

## `common_scripts` and `text_scripts`

Script-detection primitives in `rigour.text.scripts`,
implementations in `rust/src/text/scripts.rs`:

- **`codepoint_script(cp)`** — faithful Unicode Script property
  lookup. Returns `Common`, `Inherited`, real script long
  names, or `None` for unassigned / invalid codepoints. Takes
  `u32` not `char` so callers can pass `ord()` of any value
  including surrogates without TypeError at the FFI boundary.
- **`text_scripts(text)`** — set of distinct "real" scripts
  present in the text. Iterates chars, keeps only those in L\*
  (Letter) or N\* (Number) categories, excludes
  Common/Inherited/Unknown.
- **`common_scripts(a, b)`** — intersection of the above.
  Returns the scripts both strings have in common.

`common_scripts` is the cheap pruning predicate matchers reach
for. The empty-result caveat: an empty return is ambiguous
between "scripts are disjoint" (e.g. Latin vs Han) and "one
side has no real scripts" (numeric-only, punctuation-only,
empty). The two cases have different matching implications — a
numeric-only name like "007" can still match "Agent 007" via
shared NUMERIC symbols even though `common_scripts` is empty.
Pruning callers should treat empty-script inputs as wildcards
that bypass the script gate, falling through to symbol-overlap
or scoring.

A small family of script-membership predicates builds on
`text_scripts`: `is_latin`, `is_modern_alphabet`, `can_latinize`
(equivalent to `should_ascii`), `is_dense_script`. Subset checks
against named script sets defined alongside the predicates.

## ICU4X over ICU4C

The transliteration backend choice. Rationale lives in
`arch-rust-core.md` (Windows / manylinux story, build-time data
embedding). What's specific to the text-normalisation surface:

ICU4X 2.x ships per-script transliterators but does NOT ship
`Any-Latin` in `compiled_data`. We do per-script dispatch
instead. Trade-off: simpler data dependency, but mixed-script
inputs walk the string once per script present. For inputs
common in our data (single-script or Latin+one-other-script)
this is fine.

Performance characteristics on cache miss: Latin-with-diacritics
hits the ASCII fast-path and is fast. Cyrillic, Arabic,
Armenian, Georgian are within the same order of magnitude as
PyICU. CJK and three-script-mixed inputs are slower than PyICU
— ICU4X's experimental transliteration runs CLDR rules through a
pure-Rust interpreter without the decades of C++ optimisation
ICU4C has on the same rules. Cache hit rates in production
masking the cache-miss cost on most workflows.

`Transliterator` is `!Send + !Sync`, so the per-script cache
uses `thread_local!` with `RefCell`. Under the GIL this is
effectively a process-lifetime singleton.

## normality stays — explicit non-goal

`normality` provides:

- Broad-script transliteration via PyICU (`ascii_text`,
  `latinize_text`) covering scripts ICU4X doesn't ship in
  `compiled_data`: Thai, Khmer, Lao, Sinhala, Tibetan.
- Utility helpers (`category_replace`, `squash_spaces`, `WS`,
  `Categories`, `SLUG_CATEGORIES`).

Removing it means either:

- **Adding ICU4X data for the missing scripts**, which requires
  upstream `compiled_data` work or shipping our own data files.
- **Switching to `anyascii`** for ascii_text-style
  transliteration — pure-Rust, dep-free, table-lookup, ~10×+
  faster than ICU4X on cache miss. But anyascii is
  language-blind on Han (Japanese kanji collapses to Pinyin
  rather than Hepburn) and CamelCases CJK output. Quality is
  pragmatic-but-not-publication-grade; matching-OK, display-not.
- **Reimplementing the helpers** (`squash_spaces` etc.) — small
  but adds maintenance load with no benefit since we already
  depend on `normality` indirectly via FTM.

Each option has a high maintenance or quality cost relative to
the value of dropping the dep. The non-goal sticks until ICU4X
covers the missing scripts in `compiled_data` (out of our hands)
or anyascii's quality on real corpora is measured and accepted.

## Open questions

### anyascii backend swap

The strongest argument for anyascii is that `ascii_text` is
internal glue for matching — output is never displayed, just
compared. anyascii's deterministic char-by-char mapping is fine
for that. The middle path: ICU4X for `latinize_text`-shaped use
(diacritic-folding only, output preserves script-quality info),
anyascii for `ascii_text`-shaped use (pure ASCII for matching).

Decision gate: route a representative OpenSanctions export
through anyascii and measure recall. If the per-script counts
show ICU4X-and-anyascii agreement on >95% of names, anyascii
becomes the preferred backend. If significant divergence on CJK
or Indic, stay on ICU4X.

This question is also gated by whether name-matching ever
acquires language hints. Today consumers don't pass language;
the Han-Pinyin-vs-Hepburn ambiguity has no mitigation. If
language hints arrive (FTM `lang` attribute on names already
exists), anyascii becomes safer because we can route
`ja`-tagged inputs through ICU4X and everything else through
anyascii.

### `Cleanup::Slug` vs `Cleanup::Strong` for stopwords

`rigour.text.stopwords` is the only consumer of `Slug`. Slug's
distinguishing behaviour vs. Strong is preserving Lm/Mn (modifier
and nonspacing-mark categories) and deleting Cc (where Strong
turns Cc into whitespace). Stopword keys don't obviously need
Lm/Mn preserved — promoting to Strong would simplify the
variant set. Flip once stopword functions migrate to flags,
assuming the resulting wordlist is identical.

### `Cleanup::Name` variant

An earlier iteration proposed exposing `tokenize_name`'s
TOKEN_SEP_CATEGORIES + SKIP_CHARS + KEEP_CHARS as a `Cleanup`
variant. Skipped — the category logic there is entangled with
tokenisation semantics (separator vs. delete vs. keep per
category) and belongs inside `tokenize_name` rather than as a
standalone cleanup mode. Revisit only if a caller needs the
category-replacement step without the tokenise-and-rejoin step.

### Per-segment `maybe_ascii`

Today `maybe_ascii` is whole-string: if every script in the
input is in `LATINIZE_SCRIPTS`, transliterate the whole thing;
otherwise pass through unchanged. A per-segment variant would
split the input by script and transliterate only the
Latinizable segments, leaving non-Latinizable segments in their
original script. Useful for inputs like "Tokyo 東京" where the
Latin half could ASCII-fy while the Han half stays. Decide per
caller on first need; the primitive starts whole-string.

### Stopword and predicate flag migration

`rigour.text.stopwords` (`is_stopword`, `is_nullword`,
`is_nullplace`) and `rigour.names.check.is_generic_person_name`
still take a `Normalizer` callback. Post-migration they take
`Normalize` flags directly. The flag values to use are pinned
in code (the docstrings indicate
`Normalize.CASEFOLD | Normalize.SQUASH_SPACES + Cleanup.Slug`
for stopwords, `Normalize.CASEFOLD | Normalize.NAME` for
generic-person). After migration the legacy `normalize_text`,
`normalize_name`, `prenormalize_name`, and the
`org_types.normalize_display` / `_normalize_compare` shims can
all retire.

### Free-threaded Python and the `thread_local!` cache

The ICU4X transliterator cache uses `thread_local!` with
`RefCell` because `Transliterator` is `!Send + !Sync`. Under the
GIL this is effectively a process-lifetime singleton. Under
free-threaded Python (PEP 703), each OS thread pays
transliterator init separately. See `arch-rust-core.md` for the
broader free-threading question.

### Resolved (recorded so they don't get re-litigated)

- **Public transliteration surface is `maybe_ascii` /
  `should_ascii` only.** `ascii_text` and `latinize_text` are
  not exposed via PyO3. Internal Rust callers use
  `maybe_ascii`.
- **`Normalize::ASCII` and `Normalize::LATIN` removed.** Unused
  across the whole stack at port time; eliminated as dead paths
  in `rust/src/text/normalize.rs`.
- **`tokenize_name` and `normalize_name` are not duplicated.**
  Both Rust-backed; Python wrappers are thin re-exports
  (`tokenize_name`) or deprecated shims (`normalize_name`).
- **`ĸ → q` adoption.** CLDR Latin-ASCII picks `q` (phonetically
  motivated from Greenlandic / Sami Kra). rigour adopts CLDR's
  choice; override via `ASCII_FALLBACK` if ever surprising.
- **`Normalizer` and `noop_normalizer` live in
  `rigour.text.normalize`.** Adjacent to the rest of the
  normalisation surface; not in `rigour.text.dictionary` (which
  was retired).
