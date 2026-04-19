---
description: ICU4X-backed transliteration for rigour-core — architecture, benchmarks, and alternatives
date: 2026-04-19
tags: [rigour, rust, transliteration, icu4x, anyascii, performance]
---

# rigour Rust port: transliteration

This document is extracted from `plans/rust.md` so it can grow independently. It
covers everything related to ASCII / Latin transliteration in the Rust port:
why ICU4X was chosen over ICU4C, how the pipeline is structured, what the spike
found, production benchmark numbers after landing, and the evaluation of
`anyascii` as a possible alternative backend.

The broader plan (phases, architecture, open questions) lives in `rust.md`.
Both documents cross-reference each other.

## Why ICU4X Instead of ICU4C

The previous attempt (Jan 2026, `fafo-rust` branch) used `rust_icu_utrans`
which wraps ICU4C via bindgen. Problems:

- Requires ICU4C headers and libraries at build time
- Creates linking headaches for manylinux wheel distribution (must bundle or static-link ICU)
- The Python→Rust→ICU4C double-hop didn't outperform Python→ICU4C (PyICU) directly

**ICU4X** (`icu` crate v2.2.0) is the ICU team's pure-Rust rewrite:

- Compiles statically, no system dependency
- Data baked into the binary (CLDR data via `compiled_data` feature)
- Binary size with all transliteration data: **3.4 MB**
- Init time for all transliterators: **<1ms**

## Transliteration Architecture (Spike-Validated)

ICU4X `compiled_data` does NOT include `Any-Latin` (the compound transliterator
used by PyICU). It DOES include 10 script-specific transliterators. The
architecture is a manual pipeline with script detection:

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

Available built-in transliterators (BCP-47-T locale IDs). The spike verified ten
locales; in-tree probing extended the list to 22 total (see
`rust/src/text/transliterate.rs`).

| Locale ID | Script | Verified |
|-----------|--------|----------|
| `und-Latn-t-und-cyrl` | Cyrillic | spike |
| `und-Latn-t-und-arab` | Arabic | spike |
| `und-Latn-t-und-hans` | Chinese (Simplified) | spike |
| `und-Latn-t-und-grek` | Greek | spike |
| `und-Latn-t-und-hang` | Hangul | spike |
| `und-Latn-t-und-geor` | Georgian | spike |
| `und-Latn-t-und-armn` | Armenian | spike |
| `und-Latn-t-und-deva` | Devanagari | spike |
| `und-Latn-t-und-kana` | Katakana (Hiragana routes here) | spike |
| `und-Latn-t-und-hebr` | Hebrew | spike |
| `und-Latn-t-und-syrc` | Syriac | probed |
| `und-Latn-t-und-beng` | Bengali | probed |
| `und-Latn-t-und-taml` | Tamil | probed |
| `und-Latn-t-und-telu` | Telugu | probed |
| `und-Latn-t-und-knda` | Kannada | probed |
| `und-Latn-t-und-mlym` | Malayalam | probed |
| `und-Latn-t-und-gujr` | Gujarati | probed |
| `und-Latn-t-und-guru` | Gurmukhi | probed |
| `und-Latn-t-und-orya` | Oriya | probed |
| `und-Latn-t-und-ethi` | Ethiopic | probed |
| `und-Latn-t-und-thaa` | Thaana | probed |
| `my-Latn-t-my` | Myanmar (language-tagged) | probed |

**Not in compiled_data as of 2.2**: Thai, Khmer, Lao, Sinhala, Tibetan. These
pass through unchanged via a graceful `Option<Transliterator>` fallthrough in
the thread-local cache.

## Threading: `Transliterator` is `!Send`/`!Sync`

Cannot use `std::sync::LazyLock`. Options:

- `thread_local!` with `RefCell` — simplest, works with PyO3 GIL guarantee
- Per-call construction — too slow (~900µs init)
- `unsafe impl Send` — risky, transliterator may hold Rc internally

**Chosen**: `thread_local!` since Python's GIL means one thread per interpreter.
Storage is `RefCell<HashMap<&'static str, Option<Transliterator>>>` so we can
lazy-init per-script on first use and cache failures permanently.

## Spike Output Quality: 40/45 exact matches

| Difference | PyICU | ICU4X | Verdict |
|-----------|-------|-------|---------|
| Norwegian ø | `Lo/kke` | `Lokke` | ICU4X better |
| Azeri ə/Ə | `ahmad` | `?hm?d` | Fix: add to ASCII fallback table |
| Armenian w/v | `Geworg` | `Gevorg` | Both valid romanizations |
| Georgian apostrophe | curly `'` (U+2019) | ASCII `'` (U+0027) | ICU4X correct for ASCII |

**Latinize: 5/5 exact matches** (Ukrainian, Russian, Greek, Chinese, Georgian).

## Performance: Bottleneck Identified and Solved (pre-landing)

The `Latin-ASCII` built-in transliterator is 4,500 ops/sec — a bottleneck.
Replace with direct `icu::normalizer` (3.5M ops/sec) + custom fallback table.

| Step | ops/sec | Production approach |
|------|---------|-------------------|
| Script transliterator | 52,000 | Keep (built-in) |
| NFKD + Mn removal | 3,500,000 | Use `DecomposingNormalizerBorrowed` directly |
| ASCII fallback | ~millions | Custom lookup table |
| Latin-ASCII (built-in) | 4,500 | **DO NOT USE** — replaced by above |

## Post-landing benchmark results (April 2026)

Measured after landing `ascii_text`/`latinize_text` via ICU4X. Release build
(`maturin develop --release`), LRU caches busted with unique per-iteration
inputs. See `benchmarks/bench_transliteration.py` (Python) and
`rust/examples/bench_transliterate.rs` (pure Rust, no PyO3).

**FFI overhead is not the bottleneck** — a no-op PyO3 function (`_ffi_noop`,
`str`→`str`, zero work) measures 63–201 ns per call across input sizes. All the
cost below is library work, not boundary-crossing.

Cache-miss cost per call, PyICU vs rigour's Rust/ICU4X path:

| Input | PyICU (normality) | rigour (Rust/ICU4X) | slowdown |
|-------|-------------------|---------------------|----------|
| latin_diacritics | 5.71 µs | 605 ns | **0.1× — 10× faster** (ASCII fast-path dominates) |
| cyrillic_short | 6.94 µs | 9.23 µs | 1.3× |
| arabic | 10.67 µs | 14.24 µs | 1.3× |
| armenian | 8.65 µs | 8.22 µs | ~same |
| georgian | 8.84 µs | 5.70 µs | 0.65× — faster |
| greek | 11.88 µs | 35.77 µs | 3× |
| korean | 9.84 µs | 33.76 µs | 3.4× |
| japanese | 9.79 µs | 53.86 µs | 5.5× |
| chinese | 85 µs | 960 µs | **11×** |
| mixed_three | 43.76 µs | 866 µs | **20×** |

Two separable root causes (confirmed by the pure-Rust `bench_transliterate`
example matching Python numbers minus FFI):

1. **ICU4X's experimental transliteration runs CLDR rules through a pure-Rust
   interpreter; ICU4C has decades of C++ optimisation on the same rules.**
   Rust-native Chinese: 894 µs vs PyICU's 284 µs. 3× baseline slowness we cannot
   fix without upstream work on `icu_experimental`.

2. **Our pipeline re-walks the whole input once per non-Latin script present.**
   For `"Hello мир 中国"`: `text_scripts()` yields `{Latin, Cyrillic, Han}`, we
   skip Latin, then apply the Cyrillic transliterator on the full string (new
   `String` allocation, full walk), then the Han transliterator on *that* output
   (another walk, another allocation). PyICU uses a single compound `Any-Latin`
   pass. ICU4X does not ship `Any-Latin` in `compiled_data`, which is why we do
   per-script dispatch. This is the 18–20× multiplier on the `mixed_three` case.

**Why shipping it anyway is acceptable:**

- Latin-with-diacritics (the most common input in name data) is *10× faster*
  because the Python-level `isascii()` fast-path avoids FFI entirely.
- Cyrillic, Arabic, Armenian, Georgian — the scripts dominant in our sanctions
  data — are within 1.5× of PyICU.
- `@lru_cache(maxsize=MEMO_LARGE=65k)` at the Python wrapper level masks cache-miss
  cost for production workflows where name tokens recur heavily across entities.
- The Chinese/Japanese/Korean regressions are real but these are minority inputs
  in rigour's existing workflows. Revisit if profiling shows they dominate.

**Actionable optimisations if the regression starts hurting:**

- **Script-slicing**: instead of passing the whole string to each script's
  transliterator, split the input by script and only send each slice to its
  matching transliterator. Would flatten `mixed_three` from ~855µs toward the
  sum of per-script costs (~60µs). Medium effort; worth it if mixed-script input
  becomes common.
- **Manual compound transliterator**: ICU4X supports composing transliterators.
  Build a single compound at init time that dispatches internally. Medium effort,
  needs research against ICU4X 2.x API.
- **Swap backend to `anyascii`** (see next section).

## Alternative: anyascii (evaluated, not chosen yet)

[`any_ascii = "0.3.3"`](https://crates.io/crates/any_ascii) is a pure-Rust,
dep-free, table-lookup ASCII transliterator (ISC licensed, ~400–600KB rodata).
Every Unicode codepoint maps to a fixed ASCII replacement string. Covers 124k of
155k assigned codepoints (Unicode 16.0); hand-curated from BGN/PCGN, UNGEGN,
ALA-LC, ISO, Unihan, and per-language standards.

API is trivial:

```rust
use any_ascii::any_ascii;
let s: String = any_ascii("Владимир Путин"); // "Vladimir Putin"
```

**Why it's attractive**: a single two-level byte-table lookup per char. No rule
parsing, no per-script re-walks, no allocations except the output `String`.
Expected speed is 10×+ faster than ICU4X — roughly memory-bandwidth. Also
covers the scripts ICU4X leaves as identity in `compiled_data`: **Thai, Khmer,
Lao, Sinhala, Tibetan** all have mappings.

**Output quality tradeoff vs ICU4X**:

- Russian: `Владимир Путин` → `Vladimir Putin` (same as ICU4X).
- Chinese: `深圳` → `ShenZhen` (CamelCased Pinyin, no tone marks, no word
  segmentation). ICU4X produces `"shen zhen"` (space-separated, more readable).
- Korean: `김민석` → `GimMinSeok` (Revised Romanization, CamelCased). ICU4X
  produces `"gimminseog"`.
- Japanese kanji: **fails.** `高市早苗` hits the CJK table and gets Chinese
  Pinyin (`GaoShiZaoMiao`), not Japanese Hepburn (`takaichi sanae`). This is
  the biggest quality gap — anyascii cannot distinguish Han usage by language
  without a hint.
- Arabic: `بشار الأسد` → ~`bshar al'sd` (no vowel insertion). ICU4X does
  slightly better but both are lossy.
- German: `Blöße` → `Blosse` (anyascii collapses ö naively). ICU4X via our
  fallback table produces `Blosse` too, so they agree here.

**Assessment for rigour's use case**: name matching is much more tolerant of
"wrong but consistent" output than publication-quality romanization is.
Deterministic char-by-char mapping collapses both source-script and
already-romanized variants to the same ASCII form, which is exactly what
phonetic/token matchers want. The Japanese kanji limitation is real but
addressable as "route `ja`-tagged inputs through ICU4X first, then anyascii
for everything else" if and when language hints become available.

**Decision gate — not taken yet**: revisit once we have either (a) a real-world
profile showing the Chinese/mixed-three regression matters, or (b) a decision
about whether rigour consumers (nomenklatura, FTM) can provide language hints
so we can do the two-stage (`ja` → ICU4X, else → anyascii) approach cleanly.
Until then, ICU4X remains the primary path. If we do switch, `any_ascii =
"0.3.3"` would be the one-line dep addition and the wrapper would collapse to
about 10 lines of Rust.

## Cargo Dependencies

```toml
[dependencies]
icu = { version = "2", features = ["unstable", "compiled_data"] }
```

Feature `unstable` gates `icu::experimental::transliterate`. Feature
`compiled_data` bakes CLDR data into the binary.

## Test Expectations Updated from PyICU

When porting from PyICU to ICU4X, these pinned test values changed. See
`tests/text/test_transliteration.py` for the current corpus.

- Norwegian: `"Lars Lo/kke Rasmussen"` → `"Lars Lokke Rasmussen"` (ICU4X better)
- Georgian: curly apostrophe → ASCII apostrophe (ICU4X correct)
- Armenian `Mit'c'el` pinned-char (U+02BB) → ASCII `'` via fallback table
- Arabic `s?wd` (PyICU giveup) → `s'wd` (ICU4X ayn mapped to apostrophe)
- Japanese middle dot `?` (PyICU giveup) → space (anyascii-style separator)

**Dropped dep**: `pyicu` removed from `pyproject.toml`. Still pulled in
transitively via `normality`; true elimination needs the normality subsumption
tracked in `rust.md`.
