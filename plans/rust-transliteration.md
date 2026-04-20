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

- **Skip transliteration when the input is single-script.** `ascii_text` is
  called from `pick_name` (and future `analyze_names`) to produce a
  cross-script ASCII key for vote-stacking, but within a single cluster
  most candidates share one script. A cheap upfront check via
  `text_scripts(name).len() == 1` (already Rust-backed, constant-time
  lookup) could bypass the ICU4X pipeline whenever script reinforcement
  is pointless. Small effort, high-leverage — see *Downstream-port
  observations* below for why.
- **Script-slicing**: instead of passing the whole string to each script's
  transliterator, split the input by script and only send each slice to its
  matching transliterator. Would flatten `mixed_three` from ~855µs toward the
  sum of per-script costs (~60µs). Medium effort; worth it if mixed-script input
  becomes common.
- **Manual compound transliterator**: ICU4X supports composing transliterators.
  Build a single compound at init time that dispatches internally. Medium effort,
  needs research against ICU4X 2.x API.
- **Swap backend to `anyascii`** (see next section).

## Downstream-port observations (Phase 4+, `pick_name`, `tagger`)

After landing `ascii_text` (Phase 1) and starting to build larger ports
on top of it (Phase 3 org_types, Phase 4 tagger, `pick_name`), the
per-call microbenchmark numbers above understate how much
transliteration ends up costing in the real workloads.

### The thread-local cache we ended up adding

`rust/src/text/transliterate.rs::ascii_text` carries a per-thread
`HashMap<String, String>` cache, cap 131k entries, clear-on-full.
Added during the `pick_name` port when it surfaced that the Python
wrapper's `@lru_cache(maxsize=MEMO_LARGE)` was silently absorbing the
20–50 µs per non-ASCII call for Python callers, while Rust-internal
callers (pick_name, analyze_names, the tagger alias-build path) were
paying the full ICU4X cost on every lookup.

With the cache in place:

- Python callers see no regression (their own LRU already covered them,
  and a cached Rust hit is comparable to a Python dict hit).
- Rust-internal callers get the same mask, so repeat inputs within a
  hot loop are free.
- Production impact depends on workload shape. If your input has
  repetition (matcher query × many candidates: query text repeats
  across calls), hit rate is high. If your input has mostly-unique
  strings (OpenSanctions export: one pass over millions of distinct
  entity names), hit rate collapses and transliteration dominates.

This split in hit rate is what makes benchmark numbers for `pick_name`
vary from 4.5× (synthetic 25-cluster pool with reuse) to 1.3×
(synthetic unique-suffix-per-case) — same algorithm, same code, very
different ratios depending on how much the cache helps.

### Cost decomposition for a typical `pick_name` call (cache-defeated)

Per pick with ~10 candidates in mixed scripts, 100,000 picks:

| Operation | Count | Per-call | Per 100k | Fraction |
|---|---|---|---|---|
| `ascii_text` non-ASCII (full ICU4X pipeline) | ~5 | 30–50 µs | **15–25 s** | **~70%** |
| `levenshtein_pick` form matrix (~45 pairs × 1 µs) | 1 | 100 µs | 10 s | ~30% |
| `casefold` (ICU CaseMapper) | ~10 | 1–2 µs | 1–2 s | ~6% |
| `latin_share` per-char `codepoint_script` | ~150 | 50 ns | 800 ms | ~3% |

Observed Rust total: 18.5 s. Observed Python total: 24.6 s.

The 6 s gap is Python's interpreter overhead (dict operations, `for`
loops, `combinations`, PyO3 marshalling). That's the real Rust
speedup for this workload — about 25% of the total cost. Everything
else is ICU4X work that Python and Rust both pay into via the same
code path.

### What this tells us about the port's overall shape

Not every Rust port yields a big speedup. The rule-of-thumb that fell
out of this work:

- **Ports bottlenecked on Python-side FFI + dict/list operations get
  huge wins.** Phase 3 `org_types` landed at **190× faster** because
  the Python version crossed the PyO3 boundary thousands of times per
  call into `ahocorasick-rs` and did Python-level dict manipulation
  around it. Pulling the whole loop into Rust collapsed that.

- **Ports bottlenecked on actual Unicode / ICU work get modest wins.**
  `pick_name`, `string_number`, parts of the tagger alias-build all
  fall here. Both Python and Rust end up calling the same ICU4X code;
  Rust only gets to eliminate the thin Python overhead on top.

For the "make OpenSanctions export faster" motivation behind
`pick_name`, the realistic production win is the ~1.3× number, not
the ~4.5× cache-favourable one. If we want more, we have to cut
ICU4X transliteration calls, not optimise the surrounding code.

### Why this sharpens the anyascii question

The per-call microbench numbers above (Chinese 11× slower, mixed
three-script 20× slower) were defensible when we thought the cost
was bounded: "we call `ascii_text` occasionally, when we really need
it". What the downstream work exposed is that we call it *a lot* —
10 times per `pick_name` call, eventually once per name-part in
`analyze_names`, and on every alias at tagger-build time. Each call
that hits the slow path costs 30–50 µs on realistic inputs.

This flips the anyascii trade-off. Quality-wise anyascii is
"deterministic ASCII, language-blind", which for the
name-matching use case is usually *acceptable* (matching logic is
tolerant of "wrong but consistent"); speed-wise it's projected at
10–100× faster than ICU4X. The Japanese-kanji-collapses-to-Pinyin
issue is real but constrained — it only affects one script family,
and we can route `ja`-tagged inputs through ICU4X as a fallback if
we ever gain language hints.

Decision gate (revised): anyascii is now the *leading candidate* for
the next wave of transliteration work if pick_name / analyze_names
performance matters in production. The one-line dep addition and
~10 lines of wrapper code from the earlier evaluation are still
accurate. What's changed is that the evidence for needing it has
moved from "theoretical" to "measured in the downstream port".

A middle path worth considering: **ICU4X for `latinize_text`, anyascii
for `ascii_text`.** `latinize_text` is user-visible (it's used where
the output matters, e.g. display); `ascii_text` is internal glue for
matching where the output is never shown, just compared. anyascii's
deterministic-but-lossy output is fine for the latter. This lets us
keep ICU4X's higher-quality romanisation where users see it and get
the speedup where they don't.

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

**Decision gate — leaning yes, see _Downstream-port observations_ above**:
the "we have a profile showing transliteration dominates" condition is
now met. The specific next action is still a small PR: `any_ascii =
"0.3.3"` as a one-line dep and a ~10-line wrapper. The open question
is which of ICU4X / anyascii to route where — the "ICU4X for
`latinize_text`, anyascii for `ascii_text`" split proposed above is
the natural answer if we don't get language hints from consumers;
full anyascii with a `ja`-hint escape hatch is the answer if we do.

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
