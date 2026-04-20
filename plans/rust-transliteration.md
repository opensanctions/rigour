---
description: ICU4X-backed transliteration for rigour-core — architecture, benchmarks, and alternatives. Reframe (April 2026) proposes narrowing to `maybe_ascii` over known-good scripts.
date: 2026-04-20
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

**FFI overhead is not the bottleneck** — a no-op PyO3 function (`str`→`str`,
zero work) measured 63–201 ns per call across input sizes during the port.
All the cost below is library work, not boundary-crossing.

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

## Reframe: opportunistic transliteration (April 2026)

> **Superseded by `plans/rust-minimal-translit.md` (April 20, 2026).**
> The strategic-option dialogue below is retained for context; the
> concrete decision is "Keep ICU4X, narrow the callers" + cap new
> rigour-side transliteration surface at `maybe_ascii` only. See the
> minimal-translit plan for gotchas and migration path.


The preceding sections all assume the goal is "match PyICU's
`Any-Latin` in Rust, across every script, as fast as possible". That
goal is increasingly at odds with how rigour and downstream callers
actually use transliteration.

### The contradiction

On the one hand, we've spent a lot of effort trying to feature-match
PyICU across every script ICU4X ships — including Chinese, Japanese,
Korean, where both the quality gap and the perf gap are largest (11–
20× slower than PyICU, with outputs that are still lossy enough to be
questionable for matching).

On the other hand, `followthemoney-matching` logic-v2 is already
moving the *other* direction: instead of "always latinize", it uses
`can_latinize()` (`rigour/text/scripts.py:71`) to gate the call.
`rigour/territories/util.py:21-40` already follows the pattern —
walk chars, compute `can_latinize_cp` for each, only run
`latinize_text` if every cp passes. The non-Latinizable scripts are
kept in their original form for matching.

So we're simultaneously (a) building a general-purpose transliterator
in Rust and (b) deprecating the calls that would use it
general-purpose. The reframe below takes the deprecation seriously.

### Proposed primitives

- `should_ascii(text: &str) -> bool` — predicate. True iff
  transliterating `text` to ASCII produces useful output. Initial
  definition: wraps `can_latinize` (every distinguishing script in
  `LATINIZE_SCRIPTS`). Refineable per-callsite later.
- `maybe_ascii(text: &str, drop: bool) -> String` — single primitive
  that combines the check with the transform. If `should_ascii(text)`
  is true, return `ascii_text(text)`. Otherwise: return `text` as-is
  if `drop == false`, empty string if `drop == true`.

Everyone who is currently doing `if can_latinize(x): ascii_text(x)
else: x` (or `else: ""`) collapses to one call. No new behaviour, but
a single chokepoint for (a) the eventual backend swap and (b) the
ASCII fast-path.

**Open semantic question**: whole-string or per-token? `NamePart`
operates on a single token, so whole-string is fine there. For
longer strings with mixed scripts (`"Tokyo 東京"`), whole-string
returns either all-or-nothing; per-token splits at script boundaries
and transliterates only the Latinizable segments. Decide per caller
on first port; the primitive starts whole-string and we add a
per-segment variant if a caller needs it.

### Script-by-script candidate analysis

`LATINIZE_SCRIPTS` today is `{Latin, Cyrillic, Greek, Armenian,
Georgian, Hangul}` (`rigour/text/scripts.py:10`). The table below
audits every script we might reasonably consider for `maybe_ascii`,
including ones currently excluded, against both available backends.

"In set" = currently in `LATINIZE_SCRIPTS`. "ICU4X" = ships in
`icu 2.2 compiled_data` (rules probed from
`rust/src/text/transliterate.rs::SCRIPT_LOCALES`). "anyascii" = has
mappings in the `any_ascii 0.3` codepoint table. "Match-quality" is
a judgement on whether the transliterated output is useful for
name-matching, not publication-quality romanisation.

| Script | Typical languages / data source | In set | ICU4X | anyascii | Match-quality verdict |
|---|---|:---:|:---:|:---:|---|
| Latin | EN, FR, ES, DE, etc. — baseline | ✓ | identity | identity | Trivial — no transliteration needed; the ASCII fast-path covers it |
| Cyrillic | RU, UK, BG, SR, KK, MK | ✓ | ✓ | ✓ | Both backends good; outputs differ by ≤1 char on our corpus |
| Greek | EL | ✓ | ✓ | ✓ | Both good; well-defined romanisation |
| Armenian | HY (sanctions data) | ✓ | ✓ | ✓ | Both usable; Armenian w/v ambiguity present in both |
| Georgian | KA (sanctions data) | ✓ | ✓ | ✓ | Both usable; ICU4X slightly nicer apostrophe handling |
| Hangul | KO | ✓ | ✓ | ✓ | Both produce Revised Romanization; anyascii is CamelCased (`GimMinSeok` vs `gimminseog`) — equivalent for matching after casefold |
| Hebrew | HE | ✗ | ✓ | ✓ | Consonant-skeleton lossy in both. Usable for matching if "wrong but consistent" is acceptable |
| Arabic | AR, FA, UR | ✗ | ✓ | ✓ | Vowelless, lossy in both. Same caveat as Hebrew. PyICU does slightly better on vowel insertion |
| Devanagari | HI, SA, MR, NE | ✗ | ✓ | ✓ | Both usable; standard IAST-adjacent output |
| Bengali | BN, AS | ✗ | ✓ | ✓ | Both usable; niche for our data |
| Tamil, Telugu, Kannada, Malayalam | South Indian languages | ✗ | ✓ | ✓ | Both usable; niche for our data |
| Gujarati, Gurmukhi, Oriya | Indic | ✗ | ✓ | ✓ | Both usable; niche |
| Ethiopic | AM, TI | ✗ | ✓ | ✓ | Both produce standard romanisation |
| Thaana | DV (Maldivian) | ✗ | ✓ | ✓ | Niche; both work |
| Syriac | Liturgical Aramaic | ✗ | ✓ | ✓ | Niche; both work |
| Myanmar | MY (Burmese) | ✗ | ✓¹ | ✓ | Both work; language-tagged in ICU4X |
| Hiragana | JA (kana only) | ✗ | ✓² | ✓ | Hepburn, usable for matching |
| Katakana | JA (kana only) | ✗ | ✓ | ✓ | Hepburn, usable for matching |
| Han | ZH (simp + trad), JA kanji | ✗ | ✓³ | ✓³ | **Language-ambiguous.** Both default to Pinyin; Japanese kanji gets Chinese readings unless routed through a JA hint. Anyascii CamelCases (`ShenZhen` vs `shen zhen`) — equivalent after casefold |
| Thai | TH | ✗ | ✗ | ✓ | Only anyascii covers. Quality is pragmatic romanisation, not official RTGS |
| Khmer | KM | ✗ | ✗ | ✓ | Only anyascii |
| Lao | LO | ✗ | ✗ | ✓ | Only anyascii |
| Sinhala | SI | ✗ | ✗ | ✓ | Only anyascii |
| Tibetan | BO | ✗ | ✗ | ✓ | Only anyascii |

¹ Myanmar ships under `my-Latn-t-my` (language-tagged), not the
usual `und-Latn-t-und-*` form.
² Hiragana is routed through the Katakana transliterator —
ICU4X doesn't ship a distinct Hiragana→Latin transform but the
Katakana one handles both after NFKD normalisation upstream.
³ Han is the hardest case: anyascii's table and ICU4X's
`und-hans` are both one-size-fits-all Chinese Pinyin. The
Japanese-kanji-in-names case (e.g. `高市早苗`) needs a language
hint to select Hepburn instead — neither backend can do that
from codepoints alone.

**Reading the table**:

- **Scripts in the set today** all work in both backends; the
  choice of ICU4X vs anyascii is a perf/quality trade-off, not a
  coverage one. This is the bulk of the match-quality-useful
  surface area.
- **Indic + Semitic + Ethiopic** scripts are currently excluded
  but both backends handle them. If we reopen
  `LATINIZE_SCRIPTS`, adding these expands matching reach with no
  backend decision required.
- **CJK is the hard call.** Han's output is "consistent but
  language-wrong" — great for Chinese names, misleading for
  Japanese ones. This is the gap where a language hint or a
  script-kind-aware override matters more than the backend
  choice. The current Hangul-but-not-Han asymmetry in
  `LATINIZE_SCRIPTS` is defensible (Korean romanisation is
  unambiguous; Chinese isn't).
- **Thai / Khmer / Lao / Sinhala / Tibetan** are the only
  scripts where backend choice changes coverage: ICU4X doesn't
  ship them at all in `compiled_data`, anyascii does. If any of
  these appears meaningfully in our corpora, that's a point in
  favour of anyascii (or of the hybrid option).

**Recommendation gate**: a list of candidate scripts is only
decidable against real corpus data. The first concrete action on
this reframe should be a count of script distribution across a
representative OpenSanctions export — "how many entity names
contain Thai / Arabic / Devanagari / Han at all?" — to decide
which rows above are material and which are theoretical.

### What `NamePart` looks like today

`rigour/names/part.py:19-50` already does the two-step dance by
hand, with one wart. Today:

```python
self.latinize = can_latinize(form)            # line 31
...
out = ascii_text(self.form)                   # line 48 — called
                                              # unconditionally from
                                              # the .ascii property
```

The `.ascii` property runs full ICU4X transliteration *even on
non-Latinizable parts* (Chinese, Japanese, Korean). The result is
then only consumed by `.comparable` and `.metaphone`, which both
guard on `self.latinize` before using it. So the expensive
transliteration on CJK parts is always thrown away. `maybe_ascii`
makes this impossible by construction: non-Latinizable parts don't
pay the transliteration cost at all.

### Migration path

1. Add `should_ascii` and `maybe_ascii` as thin Rust primitives in
   `rust/src/text/transliterate.rs`, exposed via `_core`. Near-zero
   code; they wrap the existing `text_scripts` + `ascii_text`.
2. Switch `NamePart.__init__` + `.ascii` to a single `maybe_ascii`
   call. Drop `can_latinize` + conditional `ascii_text`. Remove the
   wasted CJK transliteration noted above.
3. Audit other callers: `rigour/territories/util.py`,
   `contrib/namesdb/namesdb/export.py`, the tagger alias-build path,
   and downstream consumers (nomenklatura, zavod, yente,
   followthemoney). For each: is it doing the "always transliterate"
   pattern, or is it already guarding? If always, does it want to
   move to `maybe_ascii`?
4. Once in-repo callers of raw `ascii_text`/`latinize_text` on
   mixed-script input are gone, the "we must feature-match PyICU"
   commitment is retired. The remaining direct callers are tests,
   `latinize_text` for user-visible output (territories generator
   scripts), and genuine lossy-romanisation use cases.

### Strategic consequences: keep or phase out ICU4X?

If `maybe_ascii` becomes the dominant surface, ICU4X's broad script
coverage is partially wasted. Options (trade-offs are the
interesting part; none is a foregone conclusion):

- **Keep ICU4X, narrow the callers.** Cheapest migration. `rust/src/
  text/transliterate.rs` stays. `ascii_text`/`latinize_text` become
  internal primitives called almost exclusively by `maybe_ascii`.
  The 3.4 MB of `compiled_data` stays in the binary but mostly
  serves `latinize_text` for the tiny number of callers (territory
  generators, user-visible displays) that genuinely want
  higher-quality romanisation. No new decisions needed.
- **Phase out rigour's ICU4X, route through normality.** Remove
  `rust/src/text/transliterate.rs` entirely; `maybe_ascii` calls
  back into `normality.ascii_text` via the Python side. Downsides:
  re-adds PyICU as a mandatory runtime dep (we just dropped it),
  loses the ASCII fast-path and the thread-local cache, and
  re-couples us to `normality`'s release cadence. Attractive only
  if we're planning to **phase out normality entirely** on a longer
  horizon — in which case this is a step backwards.
- **Phase out both, switch to anyascii.** One new dep (~600 KB),
  table-lookup per char, no rule interpretation. Quality on
  Latinizable scripts (Cyrillic/Greek/Armenian/Georgian/Devanagari)
  is within 1 char per name of ICU4X in the corpus; speed is
  projected 10–100× faster. Main loss is quality on
  `latinize_text`'s user-visible outputs for those scripts, which
  is the minority use case. Covered in detail two sections above.
- **Hybrid (ICU4X for `latinize_text`, anyascii for `maybe_ascii`).**
  The earlier "leading candidate" from *Downstream-port
  observations*, recast: `latinize_text` stays ICU4X for quality;
  `maybe_ascii` (the new primary surface) routes through anyascii
  for speed. Adds both deps. Clean split by use case, but two
  transliteration backends to maintain is not free.

The reframe changes the *weight* of each option more than it
eliminates any. "Keep ICU4X, narrow the callers" was not really
considered before because it didn't pay down the Chinese/Japanese
perf problem; now that we're explicitly *not* transliterating those
scripts, the problem disappears and this option becomes viable.

### What we need before implementing

- **Caller audit** across rigour + nomenklatura + zavod + yente +
  followthemoney. Count: how many call sites guard with
  `can_latinize` already? How many call `ascii_text`/`latinize_text`
  unconditionally? What are they using the output for (matching vs.
  display)? This determines which of the four strategic options is
  correct.
- **`maybe_ascii` semantics**: per-token or whole-string for the
  first version? Drop-or-keep behaviour when called on purely
  non-Latinizable input (return `""` vs return the original) — both
  defensible, pick per worked-example.
- **Should `can_latinize`'s LATINIZE_SCRIPTS set be reopened?**
  Currently it pins the "known-good" list; the reframe makes that
  set load-bearing. Worth a look, especially around Thai/Khmer/Lao
  which ICU4X `compiled_data` doesn't ship at all (so they pass
  through identity in our pipeline today — which means they're
  effectively in the `drop=false` bucket already, just by accident).

The next action is the caller audit, not code. This section is a
marker so the eventual implementation doesn't re-litigate the
framing.

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
