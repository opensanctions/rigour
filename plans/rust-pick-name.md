---
description: Port `rigour.names.pick.pick_name` to Rust — hot path of OpenSanctions data export, runs millions of times per export. Includes a benchmark harness and a parity / speedup scorecard.
date: 2026-04-20
tags: [rigour, rust, names, pick, performance, opensanctions]
status: plan
---

# Rust port: `pick_name`

## Motivation

`rigour.names.pick.pick_name` is called **per entity** during
OpenSanctions data export to choose the display name for downstream
publication. At OpenSanctions scale that's millions of invocations per
export run, each of which does:

- O(chars × names) `codepoint_script` lookups for Latin-share
  computation (each crosses the PyO3 boundary today since script
  detection is already Rust-backed).
- An `ascii_text` call per surface form (already Rust-backed, still a
  PyO3 crossing per name).
- O(N²) `levenshtein` calls across casefolded + ASCII-reduced forms,
  each a crossing into Python `rapidfuzz` (C++-backed but still FFI).

The Python function itself is ~80 lines of scoring logic; the wall
clock is dominated by interpreter overhead + FFI per small operation.
Moving the loop into Rust collapses all of this to **one** FFI call
per pick.

`plans/rust.md` already lists this as the Phase-6 candidate. This
doc is the concrete port plan with a measurement rig attached so the
speedup claim isn't hand-wavy.

## Spec (inferred from the Python implementation + tests)

See `tests/names/test_pick.py` for the pinned behaviours. Summary:

- **Contract**: `Vec<&str>` in, `Option<String>` out. The returned
  string must be a literal element of the input list (not a
  derived / title-cased / transliterated form).
- **Filter**: strip + casefold; drop empties.
- **Latin bias**: per-char Latin = 1.0, Cyrillic/Greek = 0.3,
  other alpha = 0.0, non-alpha skipped. `latin_share = sum /
  alpha_count`. Weight per name = `1 + latin_share`.
- **Single-Latin short-circuit**: if exactly one name has
  `latin_share > 0.85`, return it without running the centroid.
- **Cross-script reinforcement**: for each form, also index its
  `ascii_text` transliteration as an extra form (with the same
  weight) when `len > 2`. This lets `"Putin" + "Путин" + "Путін"`
  all stack onto the ASCII-form `"putin"`.
- **Case bias**: `name.title()` gets added to the form's surface
  bucket so Title Case beats ALL-CAPS / all-lower on tiebreaks.
- **Centroid**: for each form pair `(a, b)`, `sim = 1 -
  levenshtein(a, b) / max(len(a), len(b), 1)`. Each side's score
  accumulates `sim × peer_weight`. Rank descending.
- **Return path**: iterate ranked forms, within each form rank
  surfaces via unweighted centroid, return the first surface that's
  in the input.
- **Determinism**: input order mustn't affect output; Python does
  `sorted(names)` at intake. Rust must preserve this.

## Design

### Rust-side shape

```rust
// rust/src/names/pick.rs

/// Pick the best name from a bag of aliases, biased toward Latin
/// readability. Returns `None` iff no usable name survives filtering.
pub fn pick_name(names: &[&str]) -> Option<String>;
```

Internals:

- Reuse `text::scripts::codepoint_script` (already Rust) for
  `latin_share` — loop stays inside the crate, no FFI.
- Reuse `text::transliterate::ascii_text` (already Rust) — one
  allocation per name, still no FFI.
- Use the existing `rapidfuzz` crate dependency for Levenshtein
  (already in `Cargo.toml` for the in-Rust name picker — this is
  the caller we anticipated).
- `HashMap<String, f64>` for form-weights, `HashMap<String,
  Vec<String>>` for form → surfaces.

### PyO3 boundary

```rust
#[pyfunction]
#[pyo3(name = "pick_name")]
fn py_pick_name(names: Vec<String>) -> Option<String> {
    let refs: Vec<&str> = names.iter().map(|s| s.as_str()).collect();
    names::pick::pick_name(&refs)
}
```

Python `rigour/names/pick.py`:

```python
from rigour._core import pick_name
```

The existing Python helpers (`pick_lang_name`, `pick_case`,
`reduce_names`, `_levenshtein_pick`) stay Python — they're either
trivial wrappers around `pick_name` or unrelated logic. Only
`pick_name` itself moves.

### What this port deliberately doesn't change

- Behaviour is held constant. Every existing test in
  `tests/names/test_pick.py` must pass unchanged against the
  Rust-backed function.
- No API additions, no new flags.
- `pick_lang_name` and `reduce_names` keep their `pick_name` call
  — they inherit the speedup for free.

## Benchmark harness

Goal: **measure** the port, not guess.

New file `benchmarks/bench_pick_name.py`:

- Builds a pool of ~25 realistic multi-script name clusters (Putin,
  Xi, Merkel, Macron, Abe, al-Sisi, Lula, Modi, ...). Each cluster
  has 5–12 cross-script variants representing what the OpenSanctions
  `alias` / `previousName` / schema-language `name` set actually
  looks like in production.
- Generates **100,000 synthetic pick cases** using a seeded PRNG:
  - `k ~ Uniform(1, 20)` candidates per call.
  - Each candidate is sampled from a randomly-chosen cluster, with
    some cases collapsing to all-Latin minor variants (~30%), some
    all-non-Latin (~10%), the rest mixed (~60%).
- Runs **three implementations** back-to-back on the same 100,000
  cases:
  1. Python `pick_name` (current).
  2. Rust `pick_name` (new).
  3. A parity check: pick 5,000 random cases, assert
     `py_result == rust_result` on all of them.
- Reports per-implementation: total wall clock, ns/call, ops/sec,
  and speedup factor.

Running the bench: `python benchmarks/bench_pick_name.py` (no pytest
wrapping — this is a perf harness, not a unit test).

## Acceptance criteria

- All existing tests in `tests/names/test_pick.py` pass against the
  Rust-backed `pick_name`.
- The parity check on 5,000 random benchmark cases reports 100%
  agreement.
- Benchmark reports a meaningful speedup (expected ≥10×; will
  re-evaluate against numbers).
- `cargo test --manifest-path rust/Cargo.toml` includes unit tests
  for the Rust `pick_name` covering: empty input, single-name
  input, single-Latin short-circuit, cross-script reinforcement,
  case bias, determinism across input reorder.
- `cargo clippy --all-targets -- -D warnings` clean on both
  feature variants.

## Sequencing

1. Write this doc (done).
2. Write `benchmarks/bench_pick_name.py` against today's Python
   implementation only. Get the baseline number committed.
3. Implement `rust/src/names/pick.rs`. Run unit tests.
4. Wire PyO3 accessor + `.pyi` stub; swap Python shim.
5. Re-run the benchmark, now including the Rust implementation.
   Commit the speedup number in the PR description.
6. Retire the local Python scoring helpers if they become
   internal-only (`_latin_share` drops in particular).

## Out of scope

- Porting `pick_case`, `pick_lang_name`, `reduce_names` — they're
  either case-sensitive fiddly logic unrelated to scoring
  (`pick_case`), or thin wrappers around `pick_name`
  (`pick_lang_name`, `reduce_names`). Revisit only if profiling
  shows them as hot after this port lands.
- Changing the scoring algorithm. Even if we suspect the
  Cyrillic-as-0.3 constant is rough, that's a behaviour change and
  belongs in a separate doc.
- Exposing `latin_share` / `_levenshtein_pick` directly to Python.
  They're Python-side helpers today; stay that way.
