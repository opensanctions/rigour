---
description: Scope decision — rigour's only public transliteration surface is `maybe_ascii` + `should_ascii`, self-contained re-implementation over the 6 `LATINIZE_SCRIPTS`. Remove `Normalize::ASCII|LATIN`, un-expose `ascii_text`/`latinize_text`.
date: 2026-04-20
tags: [rigour, rust, transliteration, scope, normality, maybe_ascii]
status: landed
---

# Minimal transliteration: `maybe_ascii` only

Scope-decision record. Architectural backstory lives in
`plans/rust-transliteration.md`; this doc pins the minimal-scope
choice and the migration plan.

## The decision

1. **normality stays.** No effort to subsume its transliteration.
   rigour-Python is free to `from normality import ascii_text,
   latinize_text` when that's simpler.
2. **`maybe_ascii` + `should_ascii` are the only public rigour
   transliteration primitives going forward.** Exposed via
   `rigour._core` with Python-side re-exports.
3. **`maybe_ascii` is a self-contained minimalistic
   re-implementation**, not a wrapper over the existing
   `ascii_text`. Covers only the 6 scripts in
   `LATINIZE_SCRIPTS` (Latin, Cyrillic, Greek, Armenian,
   Georgian, Hangul). Everything else passes through as-is
   (`drop=false`) or becomes `""` (`drop=true`).
4. **`Normalize::ASCII` and `Normalize::LATIN` are removed.**
   Unused across the whole OpenSanctions stack (grep confirmed:
   rigour, nomenklatura, followthemoney, opensanctions, yente —
   zero hits). Removing them trims dead paths in
   `rust/src/text/normalize.rs`.
5. **`ascii_text` and `latinize_text` become non-public.** Not
   removed — still exist as Rust functions — but not exposed
   via PyO3 or through `rigour.text.transliteration`. Internal
   Rust callers are migrated to `maybe_ascii`. If anything ends
   up still needing them internally they stay as `pub(crate)`.
6. **ICU4X backend stays for now.** Switch to anyascii is a
   future follow-up once `maybe_ascii` has landed and we can
   measure the coverage gap on real data.

## New module: `text::translit`

A parallel module is added to let old and new coexist during
migration. End state: `text::transliterate` removed; everything
lives in `text::translit`.

- **`text::translit::should_ascii(text: &str) -> bool`**.
  `text_scripts(text).is_subset(LATINIZE_SCRIPTS)`. Pure-punct /
  pure-digit inputs return true vacuously. Short, zero
  allocation.
- **`text::translit::maybe_ascii(text: &str, drop: bool) -> String`**.
  - ASCII fast-path: if `text.is_ascii()`, return `text.to_string()`.
  - If `!should_ascii(text)`, return `""` (when `drop`) or
    `text.to_string()` (when `!drop`).
  - Otherwise: per-script dispatch over the 5 non-Latin
    scripts in `LATINIZE_SCRIPTS` (Cyrillic, Greek, Armenian,
    Georgian, Hangul), NFKD + strip nonspacing marks,
    `ascii_fallback` table for non-decomposable diacritics
    (ø→o, ß→ss, etc.). Same shape as current `ascii_text`,
    narrower `SCRIPT_LOCALES` table.
  - LRU cached, cap `MEMO_LARGE`, thread-local (same as the
    existing `ASCII_CACHE`).

## Migration path

Checkpointed. Each step is a self-contained change that leaves
the tree in a working state.

1. **Create `rust/src/text/translit.rs`** with
   `should_ascii` / `maybe_ascii`, unit tests for the 6 scripts +
   non-latinizable (Han, Thai) + mixed + `drop=true|false` +
   empty / whitespace edge cases.
2. **Expose via PyO3 + `.pyi`**. New `rigour._core.should_ascii`
   / `maybe_ascii`. Thin Python re-exports in
   `rigour.text.translit` (new file).
3. **Migrate `NamePart`** (`rigour/names/part.py:31,41-50`) to
   call `maybe_ascii(form, drop=false)` once instead of
   `can_latinize` + conditional `ascii_text`. Drop the
   wasted-ICU4X-call-on-CJK behaviour.
4. **Migrate `pick_name`** (`rust/src/names/pick.rs:118`) to
   call `maybe_ascii(form, drop=false)`. Non-6-alphabet text
   passes through unchanged — equivalent to "if the form
   isn't transliteratable, keep it as its own form cluster".
   Cross-script reinforcement narrows to the 6 scripts;
   Chinese/Japanese/Arabic clusters no longer get
   ASCII-unified, which is the documented narrowing.
5. **Remove `Normalize::ASCII` and `Normalize::LATIN`**:
   - Drop from `rigour/text/normalize.py` `Normalize` enum.
   - Drop from `rust/src/text/normalize.rs` bitflag + the
     `if flags.contains(…)` arms at lines 187-190.
   - Delete the two test cases in
     `tests/text/test_normalize.py:91,98` and the two in
     `rust/src/text/normalize.rs:356,362`.
   - Update the docstring example in
     `rigour/text/normalize.py:67`.
6. **Migrate `rigour/territories/util.py`** to
   `normality.latinize_text` (drops the diacritics-preserving
   rigour import — the one non-`ascii_text` internal caller).
7. **Un-expose `ascii_text` / `latinize_text`**:
   - Remove from `rigour/_core.pyi`.
   - Remove `py_ascii_text` / `py_latinize_text` + their
     module registrations from `rust/src/lib.rs`.
   - Delete or internalise `rigour/text/transliteration.py`.
     Its `ascii_text` + `latinize_text` Python wrappers no
     longer make sense (no underlying Rust export). The module
     can go away entirely; `rigour/reset.py:5,30` loses its
     cache-clear calls.
   - Delete `tests/text/test_transliteration.py` (or rewrite
     to test `maybe_ascii`).
   - Delete `tests/test_reset.py`'s transliteration lines.
8. **Delete `rust/src/text/transliterate.rs`** (or shrink to
   `pub(crate)` if any Rust-internal caller survives — audit
   after step 7). Remove the `pub mod transliterate;`
   registration in `rust/src/text/mod.rs`. Remove
   `ASCII_CACHE` — the new module has its own.
9. **Delete `benchmarks/bench_transliteration.py`** — public
   API it benchmarked no longer exists. Or rewrite to bench
   `maybe_ascii` vs normality.
10. **Update `rigour/_core.pyi`**, run `mypy --strict`, run
    `pytest`, run `cargo test + clippy + fmt`.

## Behavioural narrowings introduced

Documented so they're not surprises:

- **pick_name cross-script reinforcement narrows** — CJK,
  Arabic, Devanagari, etc. forms no longer get unified via
  ASCII-key with their Latin counterparts. They cluster
  separately. Test suite will flag if any assertion depends
  on the old broad behaviour.
- **NamePart.ascii returns None for non-LATINIZE_SCRIPTS
  input** — today it returns whatever ICU4X produced; going
  forward, `maybe_ascii(form, drop=false)` returns the form
  unchanged for non-Latinizable input, and the `.ascii`
  property filters `isalnum()` and returns None for empty.
  Downstream consumers (comparable, metaphone) already guard
  on `self.latinize` before touching `.ascii`, so this is
  pure dead-code removal.
- **Normalize flag set shrinks** — `Normalize.ASCII`,
  `Normalize.LATIN` gone. Callers that used them
  (grep-confirmed: nobody in stack) break. Bump `rigour`
  minor version.

## Gotchas (revised after user directives)

- **`ascii_text` / `latinize_text` stay as Rust functions if
  anything internal still calls them**. After migrations in
  steps 3, 4, 6 the callers are `text/normalize.rs` (removed
  in step 5) and internal test code. Expect to delete
  entirely in step 8, but verify before doing.
- **`rigour/reset.py:30`** calls `latinize_text.cache_clear()`
  and `ascii_text.cache_clear()` on the Python LRU wrappers.
  Those calls go when the wrapper module goes.
- **`rigour/text/transliteration.py:11-15`** — the Python-side
  ASCII fast-path (`if text.isascii(): return text`) in front
  of the FFI call. `maybe_ascii` gets the same fast-path in
  Rust (before the `should_ascii` check even), so the Python
  wrapper can be thinner or absent.
- **ICU4X binary size stays** — the `unstable` feature and
  `compiled_data` are still needed for the 5 non-Latin
  script transliterators `maybe_ascii` uses. Revisit with
  anyascii later.
- **`Normalize` bitflag bits** — ASCII = 4, LATIN = 5 (check
  actual values) will be removed. Bits stay reserved or
  renumber; either way it's a semver minor bump.

## Verification gate

After each migration step:

- `cargo test --manifest-path rust/Cargo.toml` — all unit
  tests pass, including the new `text::translit` tests.
- `cargo clippy --all-targets -- -D warnings` + the
  `--features python` variant.
- `make rust-fmt-check`.
- `pytest` — 369 existing tests (minus the deleted ones)
  continue passing.
- `mypy --strict rigour` — clean against the updated `.pyi`.

## Out of scope (explicitly deferred)

- **anyascii swap.** Later, once `maybe_ascii` lands and we
  can measure coverage gaps.
- **ICU4X data trim.** If we move to anyascii we drop the
  whole `compiled_data` feature.
- **Per-segment transliteration** (split on script
  boundaries within a string and transliterate segments
  independently). Whole-string is fine for first version.
- **`maybe_latinize`.** Territory-name normalisation already
  happens via normality in step 6; no other caller needs a
  diacritic-preserving variant.

## Related

- `plans/rust-transliteration.md` — architectural backstory.
  Its "Reframe" section is superseded by this plan.
- `plans/rust-pick-name.md` — pick_name port; step 4 above
  narrows its cross-script reinforcement behaviour.
- `plans/rust-normalizer.md` — `Normalize` flag design;
  step 5 above removes two of its bits.
