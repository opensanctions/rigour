---
description: Retirement schedule for the remaining `rigour/data/` Python modules as the Rust port progresses — what's done, what's left, and which port step triggers each removal
date: 2026-04-19
tags: [rigour, rust, data, genscripts, cleanup]
---

# `rigour/data/` retirement schedule

Companion to `plans/rust-tagger.md` and `plans/rust.md`. Pins the
"what goes when" question for the remaining Python modules under
`rigour/data/`.

## Already done (quick notes)

- **Step 5 — symbols JSON**: `resources/names/symbols.yml` now emitted to `rust/data/names/symbols.json`; Rust-only, no Python accessor.
- **Step 6 — territories**: full DB moved to `rust/data/territories/data.jsonl`. Python reads via `rigour._core.territories_jsonl()`. `rigour/data/territories/` deleted.
- **Step 7 — person-names corpus**: `rust/data/names/person_names.txt` landed, zstd-compressed at build time. Python-side accessor + wrapper (`rigour/names/person_names.py`) also retired.
- **Step 8 — tagger port**: `rigour/data/names/{data,org_types}.py` and `rigour/data/types.py` deleted; Python tagger collapsed to thin wrapper over Rust. `genscripts/generate_names.py` emits only JSON (no Python output paths) and inlines `OrgTypeSpec` locally.
- **Text data**: `rigour/data/text/{stopwords,ordinals,scripts}.py` all gone, read from Rust via `stopwords_list()` / `ordinals_dict()` / `codepoint_script()`.
- **Fast-path option from the earlier draft**: collapsed — step 8 accomplished the same thing directly.

Live state of `rigour/data/` today:

```
rigour/data/
├── __init__.py                   # DATA_PATH, iter_jsonl_text — stays
├── addresses/
│   ├── __init__.py
│   ├── data.py                   # FORMS — TO DO (see below)
│   └── formats.yml
├── langs/
│   ├── __init__.py
│   └── iso639.py                 # ISO tables — TO DO (see below)
├── names/
│   └── __init__.py               # empty marker — can delete
└── text/
    └── __init__.py               # empty marker — can delete
```

## Still to retire

### Empty `__init__.py` markers (trivial)

`rigour/data/names/__init__.py` and `rigour/data/text/__init__.py` are
both zero-byte stubs left over after their respective `data.py` files
were deleted. They can go in whichever next PR touches this area. One-
liner cleanup; no code depends on either as a package.

### `rigour/data/addresses/data.py` — `FORMS` mapping

Consumer: `rigour.addresses.normalize`. Holds the Python-generated
address-form alias mapping (derived from `resources/addresses/forms.yml`
by `genscripts/generate_addresses.py`). Not on the tagger roadmap;
separate port when the address pipeline moves to Rust.

Shape when it moves:

1. `generate_addresses.py` emits `rust/data/addresses/forms.json` (the
   existing `forms.yml` → JSON roundtrip, same as names/stopwords
   did).
2. Rust side owns the compiled `AhoCorasick` or equivalent for the
   address replacer.
3. `rigour/data/addresses/data.py` + `formats.yml` retired; Python
   `rigour.addresses.normalize` becomes a thin wrapper.

No plan doc exists for this yet — write one when the work starts.

### `rigour/data/langs/iso639.py` — ISO language tables

Consumer: `rigour.langs.*`. Holds `ISO3_ALL`, `ISO2_MAP`, `ISO3_MAP`.
Small (~a few KB), ASCII-only, low-priority — there's no performance
or memory motivation to move it. Port whenever language handling
otherwise gets Rust work (not currently scheduled).

If moved, the natural shape is `rust/data/langs/iso639.json` +
PyO3 accessors returning the three maps. Python side keeps
`rigour/langs/__init__.py` as a thin shim.

## Verification, when each retirement lands

- `pytest --cov rigour` passes — the retired modules had no direct
  tests; their consumers are what the suite exercises.
- `mypy --strict rigour` clean — watch for stale `from rigour.data.*`
  imports flagged as import errors.
- `python -c "import rigour.data.<removed>"` raises
  `ModuleNotFoundError` after the retirement PR.
- `make rust-data` produces the expected JSON artifacts; CI's no-diff
  check is the contract.
