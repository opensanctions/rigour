---
description: Flag-based normalize() replacing the normalizer-callback pattern — landed state, remaining migrations, and a duplication policy for cheap Python helpers
date: 2026-04-20
tags: [rigour, rust, normalization, api-design, names]
---

# rigour Rust port: normalization

Two related concerns:

1. **Duplication policy** — when to port a cheap Python function to
   Rust vs. keep a Python version alongside. Applies broadly across the
   rigour port, not just to the normalizer.
2. **Normalizer callback replacement** — flag-based
   `normalize(text, flags, cleanup)` replaces the old
   `Callable[[Optional[str]], Optional[str]]` callback shape.

The flag model, pipeline order, per-flag semantics, common compositions,
and two-distinct-uses framing live in code:

- Python surface + docstrings: `rigour/text/normalize.py`.
- Rust implementation + tests: `rust/src/text/normalize.rs`.
- User-facing breaking-change summary: `plans/migration-guide.md`.

## Part 1 — duplication policy

**When to duplicate instead of FFI:**

- Function body is ≲50 ns per call.
- Called per-token, not per-string.
- No data-sync story (static tables, pure functions).
- Small, pinned test corpus.

**Example — `tokenize_name`.** Per-character work is nanoseconds; the
PyO3 crossing cost would dwarf the compute on the 5–50-character tokens
rigour feeds it. Both sides exist: `rigour/names/tokenize.py` for Python
callers, `rust/src/text/tokenize.rs` for Rust-internal callers (the
tagger, `analyze_names`). The shared test corpus is the source of truth
— any output divergence is a test failure, fix by aligning one side,
never by pinning divergent expected values.

**Do NOT duplicate:** data-heavy functions (Aho-Corasick taggers,
transliterators, long-string distance computation), or state-ful
functions (regex compilation, lazy init, persistent caches). One side
owns; the other delegates.

**Not covered by this policy:** functions that are single-sourced in
Rust and exposed through `rigour._core` (the normalize work below is
one such case — one Rust function, one Python wrapper, no parallel
implementation).

## Part 2 — landed state

- `rigour.text.normalize.normalize(text, flags, cleanup)`.
- `Normalize` bit flags: `STRIP`, `SQUASH_SPACES`, `CASEFOLD`, `NFC`,
  `NFKC`, `NFKD`, `NAME`. `NAME` runs `tokenize_name` + `' '.join` as
  the final pipeline step, subsuming the legacy `normalize_name`
  composition.
- `Cleanup` variants: `Noop` (default), `Strong`, `Slug`. Tables copied
  verbatim from `normality.constants.UNICODE_CATEGORIES` (Strong) and
  `normality.constants.SLUG_CATEGORIES` (Slug) — small (~25 entries
  each), hard-coded in `rust/src/text/normalize.rs::action_strong` /
  `action_slug`.
- Reference-data functions updated to the flag interface:
  `rigour.names.org_types.replace_org_types_compare` / `_display` /
  `remove_org_types` / `extract_org_types`, and
  `rigour.names.tagging.tag_org_name` / `tag_person_name`. Defaults
  pinned to what production callers (nomenklatura / yente / FTM) pass
  today:
  - compare-style: `Normalize.CASEFOLD`
  - display-style: `Normalize.CASEFOLD | Normalize.SQUASH_SPACES`
  - tagger: `Normalize.CASEFOLD | Normalize.NAME` with
    `Cleanup::Noop` (tokenize_name handles categories).
- One compiled automaton per distinct `(normalize_flags, cleanup)`
  combination, cached process-wide in a `RwLock<HashMap>` on the Rust
  side. Empirically 1–2 distinct combos across the whole stack.
- Hygiene: `str.casefold()` replaces `str.lower()` in
  `rigour.langs.util.normalize_code` and
  `rigour.addresses.normalize.normalize_address` (differs on ß, Turkish
  dotted-I, Greek sigma; ASCII unchanged).

Downstream-caller migrations live in `plans/migration-guide.md`.

## Part 3 — pending

Three functions still take the old `Normalizer` callback:

- `rigour/text/stopwords.py`: `is_stopword`, `is_nullword`,
  `is_nullplace`. Default callback `normalize_text` — post-port flags:
  `Normalize.CASEFOLD | Normalize.SQUASH_SPACES` + `Cleanup.Slug`.
- `rigour/names/check.py`: `is_generic_person_name` (plus the
  deprecated `is_stopword` / `is_nullword` shims). Default callback
  `normalize_name` — post-port flags: `Normalize.CASEFOLD |
  Normalize.NAME`.

Once migrated, these get retired:

- `rigour.text.stopwords.normalize_text`
- `rigour.names.tokenize.normalize_name` (replaced by `CASEFOLD | NAME`)
- `rigour.names.tokenize.prenormalize_name` (trivially `str.casefold()`,
  replaced by `CASEFOLD`)
- `rigour.names.org_types.normalize_display` / `_normalize_compare`
- `rigour.text.dictionary.noop_normalizer` and the `Normalizer`
  type alias

Kept (domain-specific, not generic):
`rigour.addresses.normalize.normalize_address`,
`rigour.territories.util.normalize_territory_name`,
`rigour.langs.util.normalize_code`, `rigour.units.normalize_unit`,
`rigour.mime.*.normalize_*`.

## Deferred

**`Cleanup::Name` variant not landed.** An earlier draft proposed
exposing `rigour.names.tokenize`'s `TOKEN_SEP_CATEGORIES` /
`SKIP_CHARACTERS` / `KEEP_CHARACTERS` as a `Cleanup` variant. Skipped
— the category logic there is entangled with tokenisation semantics
(separator vs. delete vs. keep per category) and belongs inside
`tokenize_name` rather than as a standalone cleanup mode. Revisit if
the tokenizer itself gets ported to Rust and exposed.

## Open question

**Should stopwords stay on `Cleanup.Slug`, or promote to
`Cleanup.Strong`?** Stopwords is the only rigour consumer of `Slug`.
Slug's distinguishing behaviour vs. Strong is preserving Lm/Mn and
deleting Cc (where Strong deletes Lm/Mn and turns Cc into whitespace).
Stopword keys don't obviously need Lm/Mn preserved, so promoting might
simplify — flip once the stopword functions migrate to flags, assuming
the resulting wordlist is identical.
