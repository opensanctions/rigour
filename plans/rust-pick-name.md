---
description: Port `rigour.names.pick.pick_name` + `pick_case` + `reduce_names` to Rust — hot path of OpenSanctions data export. Design record.
date: 2026-04-20
tags: [rigour, rust, names, pick, performance, opensanctions]
status: landed
---

# Rust port: `pick_name` + `pick_case` + `reduce_names`

**Status: landed.** All three functions live in
`rust/src/names/pick.rs` and are exposed via `rigour._core` with
Python-side re-exports in `rigour/names/pick.py`. This doc keeps the
design trade-offs so the decisions don't have to be re-litigated.

## Motivation

`rigour.names.pick.pick_name` is called **per entity** during
OpenSanctions data export to choose the display name from a bag of
multi-script aliases. At OpenSanctions scale that's millions of
invocations per export run.

The Python implementation paid two costs repeatedly per call:
- Per-character `codepoint_script` FFI lookups for Latin-share
  computation.
- O(N²) `levenshtein` FFI calls for centroid scoring.

The Rust port collapses both to one FFI call per pick. Measured
speedup depends heavily on workload shape — see
`plans/rust-transliteration.md` *Downstream-port observations* for
why the realistic production win is modest (~1.3×), not the
10×+ originally hypothesised.

## Spec (inherited from the Python implementation + tests)

`tests/names/test_pick.py` pins the behaviour. Summary:

- **Contract**: `Vec<&str>` in, `Option<String>` out. The returned
  string is a literal element of the input list (not a derived
  form).
- **Filter**: strip + casefold; drop empties.
- **Latin bias**: per-char Latin = 1.0, Cyrillic/Greek = 0.3, other
  alpha = 0.0, non-alpha skipped. `latin_share = sum /
  alpha_count`. Weight per name = `1 + latin_share`.
- **Single-Latin short-circuit**: if exactly one name has
  `latin_share > 0.85`, return it without running the centroid.
- **Cross-script reinforcement**: each form also indexes its
  `ascii_text` transliteration as an extra form (same weight) when
  `len > 2`, stacking votes across scripts on the ASCII cluster.
  Skipped when `text_scripts` reports a single script across the
  whole input bag (no reinforcement possible).
- **Centroid**: weighted Levenshtein similarity via an O(M²)
  count-based algorithm (not O(N²) pair-enumeration). Tied scores
  break by first-appearance insertion order, not float-rounding
  accidents.
- **Surface pick within the winning form** uses a three-level rule
  `(latin_share DESC, case_error_score ASC, alphabetical ASC)`.
  No synthetic title-case variants injected into the surface
  bucket (the pre-port "ballot-box" hack).
- **Determinism**: input order doesn't affect output — `sorted(names)`
  at intake.

## Design notes worth preserving

### No synthetic title-case injection

The pre-port Python used `forms[form].append(name.title())` to
inflate the centroid score of whichever surface matched a title-cased
variant. This produced exact ties on balanced input (`GAZPROM × N +
Gazprom × M`) that Python broke via accidental IEEE-754 rounding
order.

Replaced with a principled `case_error_score` port of `pick_case`'s
heuristic (word-start-upper + mid-word-lower, length-normalised).
The surface rule is deterministic and reorder-invariant. Some
Python outputs differ on tied-score inputs; intentional
functional-equivalence divergence.

### Count-based O(M²) Levenshtein

Python's `_levenshtein_pick` enumerated `combinations(entries, 2)`
and accumulated into a `defaultdict(float)`. For duplicate-heavy
surface buckets (18 `"GAZPROM"` + 18 `"Gazprom"`) this did C(36, 2)
= 630 distance calls for a score that depends on only 1 unique
pair.

The Rust version dedupes first, then uses the algebraic identity:
for entries with counts `c_X, c_Y` and similarity `sim`,
`edits[X] += c_X · (c_X-1) · w_X + c_X · c_Y · sim · w_X`. Same
output, O(M²) distance calls instead of O(N²).

### `ascii_text` cache in `text::transliterate`

The `pick_name` port exposed that Rust-internal callers of
`ascii_text` were paying the full ICU4X cost per call (~30–50 µs),
whereas Python's `@lru_cache(maxsize=MEMO_LARGE)` wrapper was
absorbing it. Added a per-thread cap-131k cache inside
`rust::text::transliterate::ascii_text` so every Rust-internal
caller (pick_name, analyze_names, tagger alias-build) benefits.

### Cross-script skip

`pick_name` runs `text_scripts` over the whole input bag upfront.
If every input is in the same script, cross-script reinforcement
can't help — skip the ICU4X `ascii_text` pipeline entirely. Covered
via a `cross_script: bool` flag guarding the norm-path inside the
main loop. See `plans/rust-transliteration.md` for the per-call
cost this saves.

## Related ports

- **`pick_case` port** landed as part of the same work — avoids
  duplicating the case-quality heuristic. Used inside `pick_name`'s
  surface tiebreak AND exposed as a standalone primitive via
  `rigour._core.pick_case`. Python wrapper in `rigour/names/pick.py`
  preserves the pre-port `ValueError` on empty input.
- **`reduce_names` port** landed in the same work too. The
  `require_names` parameter (previously gated by `is_name`) was
  dropped — never exercised in production. `is_name` stays Python.
- **`pick_lang_name`** stays Python — thin language-filter wrapper
  around `pick_name`, not worth the FFI surface.

## Verification

- `cargo test names::pick` covers: empty/single inputs, single-Latin
  short-circuit, cross-script centroid, reorder determinism,
  balanced case bias, `pick_case` Turkish/German/Armenian/Greek/
  weird-mix cases, `case_error_score` orderings, `reduce_names`
  grouping and Greek case variants.
- `pytest tests/names/test_pick.py` — 14 existing Python tests
  exercise the Rust-backed path through `rigour._core`.
- `mypy --strict rigour` — clean against the updated `.pyi` stub.
