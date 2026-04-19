---
description: Design record for the AC-based name tagger port to Rust — data classification, step inventory, and the remaining downstream work
date: 2026-04-19
tags: [rigour, rust, tagger, names, symbols, ahocorasick]
status: implemented (step 9 pending)
---

# Rust-port sequence: the name tagger

**Status: steps 1–8 landed.** Implementation lives in
`rust/src/names/tagger.rs` + `rust/src/names/symbols.rs`; Python
`rigour/names/tagging.py` is a thin wrapper over `_core.tag_org_matches`
/ `tag_person_matches`. Step 9 (downstream adapter migration to
`normalize_flags=`) is the only outstanding work here, owned by the
nomenklatura / yente / FTM PRs.

Related plans:
- `plans/rust.md` — umbrella port (this is Phase 4).
- `plans/rust-symbols.md` — Symbol representation.
- `plans/rust-names-parser.md` — Phase 5 `analyze_names` pipeline.
- `plans/rust-normalizer.md` — `normalize_flags=` / `cleanup=` pattern.

## Data classification

Reference for which resources are still Python-visible after the port
and which are Rust-only. The distinction shapes what's in
`rigour._core` vs. baked into the Rust crate via `include_str!`.

| Resource | Post-port consumer | PyO3 accessor? |
|---|---|---|
| `text/stopwords.json` — STOPWORDS, NULLWORDS, NULLPLACES | Python (`rigour/text/stopwords.py`) | **Yes** |
| `names/stopwords.json` — PERSON/ORG/OBJ_NAME_PREFIXES, NAME_SPLIT_PHRASES, GENERIC_PERSON_NAMES | Python (`rigour/names/{prefix,split_phrases,check}.py`) | **Yes** |
| `text/ordinals.json` | Python (`rigour/addresses/normalize.py`) + Rust tagger | **Yes** |
| `names/symbols.json` — org_symbols, org_domains, person_symbols, person_nick, person_name_parts | Rust-only (tagger) | **No** |
| `territories/data.jsonl` (full DB, moved from `rigour/data/`) | Python (`rigour.territories.*`) + Rust tagger | **Yes** (`territories_jsonl()`) |
| `names/person_names.txt` (zstd-compressed at build time) | Rust-only (tagger) | **No** |

Rust-only artifacts still live under `rust/data/…`, still regenerate
via `make rust-data`, still covered by the CI no-diff check. They just
skip the `.pyi` stub and PyO3 export — the tagger reads them inside
the crate via `include_str!` / `include_bytes!`.

## Step inventory (what landed)

| # | Work | Landed as |
|---|---|---|
| 1 | Symbol + SymbolCategory port with Arc<str> interner | `rust/src/names/symbol.rs` |
| 2 | `text/stopwords.json` + accessors | `stopwords_list()` / `nullwords_list()` / `nullplaces_list()` |
| 3 | `names/stopwords.json` + accessors | `person_name_prefixes_list()` + 4 siblings |
| 4 | `text/ordinals.json` + accessor | `ordinals_dict()` |
| 5 | `names/symbols.json` (Rust-only) | `rust/src/names/symbols.rs` loader |
| 6 | Full territories JSONL moved under `rust/data/` | `territories_jsonl()` |
| 7 | `person_names.txt` under `rust/data/` + `build.rs` zstd compression | Rust-only access via `names::person_names::raw()` |
| 8 | Tagger itself — `rust/src/names/tagger.rs` with `Needles<Vec<Symbol>>`, `find_overlapping` (mirrors Python's `overlapping=True`), `TOKENIZE_SKIP_CHARS` alias pre-strip, `(TaggerKind, Normalize, Cleanup)`-keyed cache. Python `tagging.py` collapsed to thin wrapper. `ahocorasick-rs` dropped from `pyproject.toml` | `tag_org_matches(text, flags, cleanup)` / `tag_person_matches(text, flags, cleanup)` |

## Step 9 — downstream adapter migration (pending)

nomenklatura, yente, and followthemoney still call the tagger entry
points (`tag_org_name`, `tag_person_name`) with `normalizer=<callable>`.
Post-port, those accept `normalize_flags: Normalize` + optional
`cleanup: Cleanup` — see `plans/rust-normalizer.md` for the parameter
shape. Each downstream repo lands its own PR:

- Replace `normalizer=prenormalize_name` with
  `normalize_flags=Normalize.CASEFOLD`.
- Replace `normalizer=_normalize_compare` (squash + casefold) with
  `normalize_flags=Normalize.CASEFOLD | Normalize.SQUASH_SPACES`.
- Drop local `normalizer()` helpers that existed only to feed this
  parameter.

This is the last thing between the rigour-side port and the
single-FFI Phase 5 `analyze_names` pipeline taking over from per-
primitive calls.

## Out of scope

- **Porting `is_stopword` / `is_nullword` / `is_generic_person_name`
  to Rust.** They read the same data as the tagger but are standalone
  and benefit less from FFI reduction. Can follow the org_types
  pattern later if profiling shows them hot.
- **NamePart / Span / Name object-graph port.** The tagger takes a
  Python-owned `Name` and mutates it in place. The full port is
  `plans/rust.md` Phase 2, which runs in parallel and lands
  independently.
