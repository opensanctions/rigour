---
description: Retirement schedule for the remaining `rigour/data/` Python modules as the Rust port progresses — what stays, what goes, and which port step triggers each removal
date: 2026-04-19
tags: [rigour, rust, data, genscripts, cleanup]
---

# `rigour/data/` retirement schedule

Companion to `plans/rust-tagger.md` and `plans/rust.md`. Pins the
"what goes when" question for the remaining Python modules under
`rigour/data/` so nobody has to re-derive it each time a Rust port
step lands.

## Survey (as of this doc)

| Path | What it holds | Consumer(s) | Retires |
|---|---|---|---|
| `rigour/data/__init__.py` | `DATA_PATH`, `read_jsonl` helpers | Everyone below + `rigour.territories`, `rigour.addresses.format`, `rigour.names.tagging` | **Stays** — infra |
| `rigour/data/types.py` | `OrgTypeSpec` TypedDict | `genscripts/generate_names.py`; `rigour/data/names/org_types.py` | With `org_types.py` — see below |
| `rigour/data/names/data.py` | `ORG_SYMBOLS`, `ORG_DOMAINS`, `PERSON_SYMBOLS`, `PERSON_NICK`, `PERSON_NAME_PARTS` (five symbols-sourced dicts; the prefix + split-phrase + generic-person-names sections already moved to Rust in step 3) | `rigour.names.tagging._get_{org,person}_tagger` — the Python AC tagger | **Step 8** of `rust-tagger.md` (Rust tagger replaces Python tagger). Step 5 emits `rust/data/names/symbols.json` but doesn't kill the Python file yet because the Python tagger is still reading the `.py`. |
| `rigour/data/names/org_types.py` | `ORG_TYPES: List[OrgTypeSpec]` | `rigour.names.tagging` imports this at line 94 to build `ORG_CLASS` symbols from the `generic` field. The four `replace_org_types_*` / `extract` / `remove` functions are already Rust-backed and read `rust/data/org_types.json` directly — only the tagger's ORG_CLASS symbol pass still reads the Python list. | **Step 8** (Python tagger goes away) |
| `rigour/data/addresses/data.py` | `FORMS` address-form mapping | `rigour.addresses.normalize` | Later, separate port (address pipeline isn't on the tagger roadmap) |
| `rigour/data/langs/iso639.py` | `ISO3_ALL`, `ISO2_MAP`, `ISO3_MAP` | `rigour.langs.*` | Later, separate port; tables are small + ASCII, low priority |
| `rust/data/territories/data.jsonl` *(moved)* | Full territory records (code, QID, parent, ISO codes, names, jurisdiction flags) | `rigour.territories.*` via `rigour._core.territories_jsonl()`; Rust tagger reads `territories::raw()` directly | **Moved** (not retired). Previously at `rigour/data/territories/data.jsonl`; now Rust-owned at `rust/data/territories/data.jsonl`. Python consumers read through a PyO3 accessor. Retired the earlier plan of emitting a stripped name-subset alongside — full records travel together and the tagger picks out what it needs at build time. |

## What each step takes out of `rigour/data/`

### Step 5 (Rust-only `symbols.yml` → `rust/data/names/symbols.json`)

**Nothing leaves Python**. Step 5 emits the JSON and exits; the
Python tagger keeps reading `rigour/data/names/data.py` until step 8.
Explicit intermediate state by design — the JSON is inert scaffolding
for step 8.

### Step 6 (territories)

**The full territory database moves to `rust/data/`.** Earlier drafts
of the plan proposed emitting a stripped name-subset alongside the
existing Python-owned `data.jsonl`; we scrapped that in favour of
moving the whole file and having `rigour.territories.*` read through
`rigour._core.territories_jsonl()`. Single source of truth, and the
Rust tagger's name-subset slicing happens at build time on the same
records the Python side sees.

`rigour/data/territories/` is gone after this step — the only thing
under `rigour/data/territories/` was `data.jsonl` + an `__init__.py`
marker, both retired.

### Step 7 (person-names corpus)

Already landed — `rust/data/names/person_names.txt` is the Rust-owned
artifact; the pre-port path `rigour/data/names/persons.txt` is gone.

### Step 8 (Rust tagger)

**Three files retire together:**

- `rigour/data/names/data.py` — no more Python consumer.
- `rigour/data/names/org_types.py` — tagger was the last consumer.
- `rigour/data/types.py` — `OrgTypeSpec` is only imported by
  `genscripts/generate_names.py` (which inlines the TypedDict locally
  post-retirement) and by the already-retired `org_types.py`.

After step 8, `rigour/data/names/` contains only `__init__.py`
(empty marker) — which can also go.

`genscripts/generate_names.py` in the step 8 PR:

- Drops the `generate_symbols_data_file()` function entirely.
- Drops the `rigour/data/names/org_types.py` emission (only the
  `rust/data/org_types.json` emission remains).
- Inlines `OrgTypeSpec` locally (it's a 4-field TypedDict; no reason
  to cross a now-retired rigour data module).

## Fast-path option — retire `rigour/data/names/*` **before** step 8

Two small changes let us retire the whole `rigour/data/names/`
directory ahead of the tagger port. Worth doing if we don't want the
`rigour/data/` tree to look half-migrated while step 8 is pending.

### Move 1: expose `org_types_specs()` via `_core`

Add a PyO3 accessor:

```rust
#[pyfunction]
fn org_types_specs() -> Vec<OrgTypeSpec> { /* clone the LazyLock'd Vec */ }
```

which returns the parsed `rust/data/org_types.json` as
`list[dict[str, str | list[str]]]` on the Python side. Rewire
`rigour/names/tagging.py:94` to use it instead of
`from rigour.data.names.org_types import ORG_TYPES`. Then delete
`rigour/data/names/org_types.py` and the `generate_org_type_file`
Python-write path. `rigour/data/types.py` can go too if
`OrgTypeSpec` moves to a local definition in genscripts.

Handful of lines; FFI cost is one allocation per tagger build (which
happens once per process under `@cache`).

### Move 2: expose symbols via `_core`

Add five accessors — `org_symbols_dict()`, `org_domains_dict()`,
`person_symbols_dict()`, `person_nick_dict()`,
`person_name_parts_dict()` — each returning
`dict[str, list[str]]` from `rust/data/names/symbols.json`. Rewire
the two tagger builders in `rigour.names.tagging` to read through
those. Drop `generate_symbols_data_file` from genscripts. Delete
`rigour/data/names/data.py`.

This is step 5 of `rust-tagger.md` but with Python consumers wired
up (vs. the current "Rust-only" framing). If we take this route,
update `rust-tagger.md` step 5's table entry accordingly.

### Trade-off

- **Defer to step 8**: intermediate state is ugly (`rigour/data/names/`
  still exists but its contents are only loaded by the soon-to-go
  Python tagger), but the step-8 PR is smaller and cleaner.
- **Do moves 1+2 now**: `rigour/data/names/` disappears in a dedicated
  small PR; step 8 is then just "port the tagger logic" with no data
  cleanup in the same commit.

Preferred: **do move 1 now** (small, cleanly retires two files), and
leave `data.py` alone until step 5 / step 8. Move 2 can wait — it's
only marginally cleaner than the current state and duplicates work
that step 8 would have done anyway.

## What happens to `rigour/data/`

After step 8 + move 1:

```
rigour/data/
├── __init__.py                # DATA_PATH, iter_jsonl_text
├── addresses/
│   ├── __init__.py
│   └── data.py                # FORMS (still Python)
└── langs/
    ├── __init__.py
    └── iso639.py              # ISO tables (still Python)
```

Two remaining Python-owned data assets, each with its own future-port
story outside the tagger sequence. The `names/`, `text/`, and
`territories/` subdirectories are gone.

## Verification, when each retirement lands

- `pytest --cov rigour` passes — the retired modules had no direct
  tests; their consumers in `rigour.names.*` are what the test suite
  exercises.
- `mypy --strict rigour` still clean — watch for stale
  `from rigour.data.*` imports flagged as import errors.
- Manual: `python -c "import rigour.data.names.data"` raises
  `ModuleNotFoundError` after the retirement PR.
- `make rust-data` produces the expected JSON artifacts; CI's
  no-diff check remains the contract.
