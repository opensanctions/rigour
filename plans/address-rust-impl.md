---
description: Implementation plan for the Rust address comparison function designed in address-rust.md — phased build from eval harness through Rust analysis pass, D6 scorer, PyO3 surface, corpus tuning, and downstream adoption.
date: 2026-09-01
tags: [rigour, addresses, rust, matching, implementation]
status: drafting
---

# Address comparison in Rust: implementation plan

Implements the design in [address-rust.md](address-rust.md) (decisions
D1–D6). Deliverables: `compare_addresses` (score / match_type /
explanation) and `address_fingerprint`, both Rust-backed, plus the
evaluation loop that tunes the scorer against
`contrib/address_bench/cases.csv`.

## Implementation decisions to settle en route

Flagged here so each phase knows what it must resolve; none blocks
Phase 0–1 start:

- **Entry granularity**: pairwise `compare_addresses(query, result)`
  for MVP — the Rust-side LRU makes the list×list loop in nomenklatura
  cheap without a batched API. Revisit only if FFI overhead shows up
  in profiling.
- **Result type**: small frozen pyclass vs tuple. Leaning pyclass
  (`score`, `match_type`, `explanation` attributes) — mirrors how the
  name pipeline returns evidence objects and reads better at the
  nomenklatura call site.
- **Tokenizer**: resolved — a dedicated `tokenize_address` with its
  own category table (exposed as `Normalize::ADDRESS`), deliberately
  duplicated from `tokenize_name` since the two are expected to
  diverge. Initial deltas match the Python address normalizer: Mc
  separates, `&` and `№` are kept as token content (making both live
  keyword needles). Any further tokenizer expansion (e.g. a
  "separate into own token" action so glued `№17` splits and the `№`
  needle fires) waits until the Rust scorer runs end-to-end in the
  Phase 4 eval — change the table only against a benchmark delta.
- **Territory names in the tagger**: strong names only at first (the
  Python keyword table already skips weak names for FP reasons); weak
  names only if the corpus shows recall left on the table.
- **Compound numbers**: split "17/1" into components vs keep
  structured. Start by splitting; the `unit_differs` slice arbitrates.
- **Cache crate**: a mutex-wrapped `lru` vs `quick_cache`/sharded.
  Start simple; it's ~5k entries of small structs.

## Phase 0: evaluation harness (pure Python, no rigour changes)

The corpus exists; the measurement loop does not. Build it first so
every later phase has a number.

- `contrib/address_bench/evaluate.py`: reads `cases.csv`, runs a
  named scorer over all pairs, reports AUC overall and per
  `category` × `quality` slice, plus a fixed-threshold confusion
  summary. Baselines to wire in from day one:
  - current `nomenklatura.matching.compare.addresses._address_match`
    logic (reimplemented locally over raw strings to avoid the
    EntityProxy scaffolding),
  - current `ftm` `AddressType.compare` (normalize + levenshtein).
- `Makefile` target (`make evaluate SCORER=...`).
- **Gate**: baseline numbers recorded (in eval output, referenced from
  the bench README if useful — not in this plan).

## Phase 1: Rust analysis pass (internal only)

New module `rust/src/addresses/` — no PyO3 exposure yet beyond what
tests need.

- `token.rs`: `AddressToken { surface, ascii, class }` — the
  `NamePart` shape: `surface` is the post-casefold token text,
  `ascii` the analysis-time narrow transliteration (`None` when
  already ASCII or script not admitted; a `comparable()` accessor
  falls back to surface), and the class payload *is* the canonical
  form — no generic normalized field. `TokenClass::{Number, Keyword,
  Territory, Term, Text}`: `Number` carries the parsed value (via
  `text::numbers`), `Keyword` the canonical form, `Territory` the
  code set, `Term` the translation symbol (D6 annotations; lands as
  a stub variant first). Transliteration at analysis time (not
  compare time) so the Phase 3 LRU amortizes it across the 1×N
  comparison pattern.
- `analyze.rs`: casefold/normalize → tokenize → tag. Produces
  `Address { tokens, scripts }`.
- `tagger.rs`: one `Needles`-based tagger (pattern from
  `names/tagger.rs`, including its serde `TerritoryRecord` JSONL walk)
  over three alias sources: `forms.yml` keywords → canonical form,
  translation terms → symbol, territory strong names → codes.
  Multi-token aliases need span handling — `find_overlapping` +
  longest-match-wins, as in the org-types matcher.
- Data plumbing: extend `genscripts/generate_addresses.py` to emit
  `rust/data/addresses/forms.json` (and `terms.json` once the
  translation resource exists — a sibling of `forms.yml` under
  `resources/addresses/`, same shape, per D6). Wire into `make build`;
  embed via `build.rs` zstd only if size warrants (forms are small —
  plain `include_str!` is fine and the convention allows it for small
  files).
- Rust unit tests per component; corpus rows from the design doc
  (transliterated Cyrillic, keyword-dense US strings, the neardupe
  examples) as fixture cases.
- **Gate**: `cargo test` green; `cargo clippy --all-targets`
  (± `--features python`) clean; `make build` idempotent.

## Phase 2: scorer, grown iteratively against the benchmark

Course correction: the earlier channel/gate prescription piled up
heuristics with no evidence any individual one pays. Instead the
scorer starts as the simplest possible mechanism running end-to-end
against `cases.csv`, and every rule after that is introduced alone
and justified by a measured delta. The channel design below survives
only as a hypothesis backlog.

**v0 (done)**: `rust/src/addresses/compare.rs::compare` — normalize
both sides with `CASEFOLD | ADDRESS`, whole-string Levenshtein
similarity with a 20%-of-shorter-side edit budget. Exposed as
`rigour._core.compare_address` (singular — `compare_addresses` is
reserved for a possible list×list entry point); `SCORER=rust` in the
bench. AUC 0.5505 — parity with the ftm baseline confirms the wiring.

**Iteration protocol**, one rule at a time:

1. Implement the single change in `compare.rs`.
2. `make develop` (release build — debug is ~100× slower through
   ICU), then `make -C contrib/address_bench evaluate SCORER=rust`.
3. Record overall AUC, STRONG-only AUC, best-threshold accuracy and
   the targeted slice in the results table in
   `contrib/address_bench/README.md`.
4. Keep if overall AUC or the targeted slice improves without
   materially hurting the rest; revert if it doesn't pay. One commit
   per kept increment, numbers in the commit message.

Tunable constants stay inline in `compare.rs` until enough survive
to justify a `params.rs`.

**Increment ladder** (hypotheses, reorder/drop on evidence):

1. Token alignment: greedy best-pair over `analyze()` tokens'
   `comparable()` forms, score = matched/total weight, weight ∝
   token length (`reordered_fields`, `translit_cyrillic`).
2. Number strictness: Number tokens match only on exact ASCII-folded
   surface digit strings (`fold_digits` beside `string_number`;
   per-char `to_digit(10)` — f64 round-trip erases leading zeros);
   penalty when both sides hold unmatched numbers
   (`house_number_differs`, `unit_differs`).
3. Keyword canonical matching: canonical-to-canonical at full
   credit; unmatched keywords fuzzy on surface at reduced weight
   (`abbreviation`).
4. Territory code matching: overlap on code sets (`different_city`).

**Backlog** — only if a slice's failures demand it: postcode prefix
rule, territory name-variant fallback (incl. weak names), subset cap,
parent-hierarchy containment, stopword class, translation terms,
unmatched-number-pair penalty tuning, MatchType/explanation surface.

## Phase 3: PyO3 surface + Python wrappers

Starts once the Phase 2 ladder converges. The minimal
`_core.compare_address` float entry point already exists for the
bench; this phase builds the public surface on whatever the scorer
turned out to need.

- `lib.rs`: `compare_address(query: &str, result: &str)` →
  result pyclass; `address_fingerprint(text: &str)` →
  `Option<String>`. Both run analysis + scoring under
  `py.allow_threads`; analyzed `Address` memoized in a concurrent
  LRU (~5k, keyed on raw string) shared by both entry points (D4).
- Fingerprint serialization per the design leaning: hard
  normalization (numbers as parsed numerals, territory codes,
  canonical keyword forms); ordering policy resolved here (the last
  open fingerprint question — decide with the blocker and `node_id`
  consumers in mind, default order-preserving).
- Python side: `rigour/addresses/compare.py` thin wrappers with
  Google-style docstrings; exports in `rigour/addresses/__init__.py`;
  `rigour/_core.pyi` stubs; `::: rigour.addresses.compare` in
  `docs/addresses.md`; `mkdocs build --strict`.
- The three existing normalize functions are untouched (D5).
- **Gate**: `pytest --cov rigour` and `mypy --strict rigour` green
  after `make develop`; docs build clean.

## Phase 4: final evaluation

Mostly subsumed by the Phase 2 iteration protocol — the scorer is
tuned as it grows. What remains here is the acceptance snapshot and
fingerprint work. Targets:
  - overall AUC beats both baselines;
  - large FP reduction on `house_number_differs` / `unit_differs` /
    `different_street` vs the nomenklatura baseline;
  - no material recall loss on `translit_cyrillic` /
    `punctuation_only` / `abbreviation`;
  - `block_neardupe` residual FPs are *expected* (role-tagging is v2)
    — record the number as the v2 motivation;
  - `subset` rows score in the capped band with
    `match_type: subset`.
- Fingerprint validation: false-merge rate of hard normalization on
  the non-match strata (per the design's fingerprint caveat).
- Quick perf check with a release build (`make develop`, not debug):
  batch of corpus pairs, target comfortably-inner-loop timing; the
  LRU hit path should dominate for the 1×N pattern.
- Seed the translation-terms resource (`resources/addresses/`) from
  corpus failures surfaced here — precision-first, small.
- **Gate**: numbers recorded; tunables frozen for MVP.

## Phase 5: downstream adoption (separate repos, separate PRs)

Sketch only — each lands after a rigour release:

- **nomenklatura**: `matching/compare/addresses.py` calls
  `rigour.addresses.compare_addresses` per pair; score/explanation map
  onto `FtResult(score, detail)`; the `lru_cache` wrapper goes away
  (cache now lives in rigour). logic_v1/erun keep whatever behavior
  their frozen models need — check before touching.
- **followthemoney**: `AddressType.compare` → `compare_addresses`;
  `node_id` → `address_fingerprint` (re-keying accepted per design).
- **blocker tokenizer / erun birth-place**: stay on the Python
  normalizers (D5); fingerprint migration is its own later change.

## Cross-cutting checklist

- `make build` after any `resources/` edit; commit regenerated
  artifacts (CI diffs).
- `make rust-fmt`; clippy with and without `--features python`.
- Rebuild extension (`make develop` / `make develop-debug`) before
  pytest/mypy after Rust edits; release build for anything timed.
- `rigour/_core.pyi` kept in sync with every new PyO3 entry point.
- New public functions: full Google-style docstrings (the docstring
  is the docs), autorefs cross-links, every parameter documented.
