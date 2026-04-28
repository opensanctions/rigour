# name_comparison: harness for the name-distance comparator

A test harness for iterating on the name-distance scoring core
under `rigour/names/compare.py`. Loads labelled name pairs from
`cases.csv`, runs them through a comparator, and prints a
confusion matrix sliced by case group and category.

The design context lives in `plans/weighted-distance.md` (this
harness is phase 1 of the migration path) and
`plans/name-screening.md` (industry context on how scores are
interpreted).

## Files

- `cases.csv` — labelled name-pair test set, schema documented
  below. **Source of truth.** Hand-edit to add cases, fix
  labels, refine categories.
- `run.py` — CLI runner. Two modes (mutually exclusive):
  - `-c <comparator>` runs a named comparator over `cases.csv`,
    stores the per-case result in `run_data/`, and prints the
    summary.
  - `-s <run.csv>` re-renders the summary from a stored run
    CSV. Useful for re-thresholding (`-t 0.85`) and comparing
    runs without re-executing.
- `run_data/` — timestamped per-case dumps from `-c` runs
  (`<comparator>-YYYYMMDD-HHMMSS.csv`). Gitignored — commit
  selectively if a particular run is meaningful.

## Running

```bash
# from the rigour repo root

# Run the levenshtein baseline, store + summarise.
python contrib/name_comparison/run.py -c levenshtein

# Re-summarise a stored run at a tighter threshold.
python contrib/name_comparison/run.py \
    -s contrib/name_comparison/run_data/levenshtein-20260428-163103.csv \
    -t 0.85

# Run quietly (just dump, no console summary).
python contrib/name_comparison/run.py -c levenshtein --quiet

# Diff two runs to see which cases flipped.
qsv diff \
    contrib/name_comparison/run_data/levenshtein-20260428-163103.csv \
    contrib/name_comparison/run_data/comparable-20260428-170012.csv
```

Adding a new comparator: implement a `Callable[[str, str], float]`
in `run.py` and register it in the `COMPARATORS` dict. Each
comparator is one entry. Iterating on the spec is then "add a
new comparator, run it, diff the per-case CSV against the
previous run."

## Schema (v1)

`cases.csv` columns:

| Column       | Required | Notes |
|--------------|----------|-------|
| `case_group` | yes      | Source/corpus tag (`nk_checks`, `nk_unit_tests`, future: `qarin_negatives`, `un_sc_positives`, `us_congress`, …). |
| `case_id`    | yes      | Stable ID within group. Composite key is `(case_group, case_id)`. |
| `schema`     | yes      | FtM schema name. Drives `analyze_names`'s `NameTypeTag`. Currently used: Person, Company, Organization, LegalEntity, Vessel. |
| `name1`      | yes      | Query-side name. Single string; analyze_names infers tags. |
| `name2`      | yes      | Result-side name. |
| `is_match`   | yes      | `true` / `false`. Ground-truth label. |
| `category`   | optional | Mutation/heuristic class for slicing reports (e.g. `Character Deletion`, `friedrich_fps`). Blank if unlabelled. |
| `notes`      | optional | Free-text human-readable comment. Used for traceback to source tests, etc. |

### v2 (deferred)

Will extend with optional tagged-name-part columns
(`name1_first`, `name1_last`, `name1_middle`, …) for cases
where input is structured — modelling the well-tagged
customer-record scenario (KYC at onboarding). Add new sources
under their own `case_group`.

## Adding cases

Edit `cases.csv` directly. The file is the canonical record;
no build step regenerates it. To bring in cases from a new
external source, write a one-shot script that emits rows in
the schema above and append them. Don't keep that script in
the repo unless re-running it makes sense (most ports are
write-once).

When adding rows manually:

- Pick a unique `case_id` within the group (zero-padded
  integer is fine).
- Pick a `case_group` for the source. New groups don't need
  registration; the harness slices by whatever values appear.
- For ambiguous ground-truth (component-test scores diverge
  from full-matcher verdicts, gendered-variant pairs), prefer
  the full-matcher reading. When in doubt, leave the case out.

## Inspecting `cases.csv` with qsv

`qsv` (CLI CSV tool) is installed locally. Useful queries:

```bash
# row counts and column list
qsv count   contrib/name_comparison/cases.csv
qsv headers contrib/name_comparison/cases.csv

# distribution by case_group, schema, is_match
qsv frequency -s case_group,schema,is_match contrib/name_comparison/cases.csv | qsv table

# all labelled categories (skip blanks)
qsv search -s category '\S' contrib/name_comparison/cases.csv \
    | qsv frequency -s category --limit 0 \
    | qsv table

# pretty-print a row range
qsv slice -s 100 -e 110 contrib/name_comparison/cases.csv | qsv table

# all Vessel cases
qsv search -s schema 'Vessel' contrib/name_comparison/cases.csv | qsv table

# all positive-match cases involving non-ASCII
qsv search -s name1 '[^\x00-\x7f]' contrib/name_comparison/cases.csv \
    | qsv search -s is_match 'true' \
    | qsv table

# diff per-case output between two iteration runs (once run.py exists)
qsv diff iteration_a.csv iteration_b.csv
```

`qsv pivot` and `qsv sqlp` aren't in the local build; for
crosstabs use `qsv frequency` on multiple columns, or process
post-hoc.

## Sources

- `nk_checks` (226 rows) — ported from
  `nomenklatura/contrib/name_benchmark/checks.yml`. The
  full-matcher's regression test set, repurposed for
  name-distance evaluation. `category` carries the original
  YAML `label` field where present, blank otherwise.
- `nk_unit_tests` (84 rows) — ported from
  `nomenklatura/tests/matching/`. Two sub-sources:
  - 27 cases from the `CASES` list in `test_logic_v2_cases.py`
    — full-matcher tests with explicit `matches: bool` ground
    truth. `category=logic_v2_cases`.
  - 57 hand-curated cases derived from per-component tests in
    `test_names.py`, `test_logic_v2_names.py`, and
    `test_name_based.py`. Each was translated from a
    score-threshold assertion (e.g. JW > 0.9, Levenshtein <
    0.7) into an unambiguous `(name1, name2, is_match)`
    triple. Cases with gendered-variant ambiguity (e.g.
    Michel/Michelle) were excluded — the per-component score
    and the full-matcher verdict can disagree, and
    `nk_checks` already records those. `notes` carries the
    originating test function; `category` groups by sub-test
    (e.g. `friedrich_fps`, `obama_tps`).

Planned additions:

- `qarin_negatives` / `un_sc_positives` / `us_congress` —
  port from
  `yente/contrib/candidate_generation_benchmark/fixtures/`.
