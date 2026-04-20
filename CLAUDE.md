This library contains data validation and cleaning routines that are meant to be precise. These methods are supported by resource data. The resource data is derived from real-world datasets and meant to cover common cases of data variations in corporate registries, and AML/KYC screening data.

## Architecture

rigour is a hybrid Python + Rust library. The Python package under
`rigour/` is the public surface; a Rust crate under `rust/`
(`rigour-core`) is compiled by maturin into the private
`rigour._core` extension module. Importers should always go through
the nominated Python modules (`rigour.text.*`, `rigour.names.*`,
`rigour.territories.*`, `rigour.addresses.*`, `rigour.ids.*`, …);
`rigour._core` is an implementation detail and may change shape
between versions.

### What lives in Rust

| Area | Python entry point | Rust module |
|---|---|---|
| Phonetics (`metaphone`, `soundex`) | `rigour.text.phonetics` | `rust/src/text/phonetics.rs` |
| Unicode scripts (`codepoint_script`, `text_scripts`, `can_latinize`) | `rigour.text.scripts` | `rust/src/text/scripts.rs` |
| Transliteration (`should_ascii`, `maybe_ascii` — narrow, 6 admitted scripts) | `rigour.text.translit` | `rust/src/text/translit.rs` |
| Flag-based normalisation (`normalize`, `Normalize`, `Cleanup`) | `rigour.text.normalize` | `rust/src/text/normalize.rs` |
| Tokenisation (`tokenize_name` — Rust version) | — (internal; Python copy still lives at `rigour.names.tokenize.tokenize_name`) | `rust/src/text/tokenize.rs` |
| Numeric-string parsing (`string_number`) | `rigour._core.string_number` (no Python wrapper) | `rust/src/text/numbers.rs` |
| Org-type replacement (`replace_org_types_compare` / `_display`, `remove_org_types`, `extract_org_types`) | `rigour.names.org_types` | `rust/src/names/org_types.rs` + `matcher.rs` |
| AC name tagger (`tag_org_name`, `tag_person_name`) | `rigour.names.tagging` | `rust/src/names/tagger.rs` |
| Name picking (`pick_name`, `pick_case`, `reduce_names`) | `rigour.names.pick` | `rust/src/names/pick.rs` |
| `Symbol` / `SymbolCategory` | `rigour.names.symbol` (re-exports Rust class) | `rust/src/names/symbol.rs` |
| Territories database | `rigour.territories.*` | `rust/src/territories.rs` (reads the JSONL blob) |

Broad-script transliteration (Han / Arabic / Devanagari / …) is
deliberately **not** in Rust — internal callers in `rigour.names.part`,
`rigour.addresses.normalize`, `rigour.ids.strict`,
`rigour.territories.util` call `normality.ascii_text` /
`normality.latinize_text` directly. `rigour.text.translit.maybe_ascii`
is the minimal self-contained primitive over Latin / Cyrillic / Greek
/ Armenian / Georgian / Hangul; non-admitted scripts identity-pass
(`drop=False`) or return empty (`drop=True`).

### Data resources

Source of truth lives under `resources/` (YAML + a few text blobs).
`genscripts/` regenerates per-consumer artifacts under `rust/data/`
(e.g. `rust/data/names/stopwords.json`,
`rust/data/territories/data.jsonl`,
`rust/data/names/person_names.txt`) — these are committed. Large
blobs (person-names corpus, territories JSONL) get zstd-compressed
at crate-build time by `rust/build.rs` and embedded into the binary
via `include_bytes!`.

The **Python-side** `rigour/data/` directory is mostly drained: the
wordlist / stopword / ordinals / names / territories / org-types
tables all moved to Rust and are read via `rigour._core.*_list()` /
`rigour._core.*_dict()` accessors. Two Python data modules are still
there because their ports haven't happened yet: `rigour/data/langs/
iso639.py` (ISO-639 tables for `rigour.langs`) and
`rigour/data/addresses/` (format templates for `rigour.addresses`).
Treat them the same as any Python source — not a pattern to
replicate for new data.

`make rust-data` regenerates everything under `rust/data/` from
`resources/`. CI runs it and fails on diff, so after editing anything
under `resources/` you need to run `make rust-data` and commit the
regenerated artifacts.

### Dev workflow for Rust-touching changes

- `make develop` → `maturin develop --release` rebuilds the extension
  into your active venv. Always use release builds for benchmarks and
  any performance testing — ICU4X's trie-heavy paths are ~100× slower
  in debug.
- `make develop-debug` is the fast-iteration alternative when you
  don't care about runtime speed of the compiled code.
- After editing `rust/src/**`, rebuild with `make develop` (or
  `make develop-debug`) before running `pytest` / `mypy`, otherwise
  tests will be running against the previous `.so`.
- `rigour/_core.pyi` is the type stub for the extension; update it
  whenever you add / change a PyO3 entry point. `rigour/py.typed`
  already marks the package typed for downstream `mypy --strict`.

## Precision

* When supplementing the YAML resources in this directory, always prioritise precision over quantity.
* In alias/symbol mappings, make sure to include only aliases that would be commonly used in a business database.
* In mappings where common misspellings or variations are supplied, propose variants found in contractual documents, such as partial abbreviations, misspellings, simplifications, etc.

## Languages

* Our resources should target always supporting the following languages: English, French, Spanish, Russian, Ukrainian, Arabic, Simplified Chinese, Korean, Japanese, Portuguese (Brazilian and European), Turkish, Polish, German, Swedish, Norwegian, Danish, Lithuanian, Estonian, Finnish, Hungarian, Dutch

## Python 

* Generate fully-typed, minimal Python code.
* Always explicitly check `if x is None:`, not `if x:`
* Run tests using `pytest --cov rigour`
* Run typechecking using `mypy --strict rigour`

## Rust

* Run `make rust-fmt` before committing any Rust changes — CI runs
  `cargo fmt --check` and fails on drift. `make rust-fmt-check`
  mirrors the CI check locally.
* Run `cargo clippy --all-targets -- -D warnings` (both with and
  without `--features python`) before committing — CI treats
  warnings as errors.

## Docstrings and mkdocs

Public API docs are built with mkdocs Material + mkdocstrings (Python
handler). The `docs/*.md` pages are thin — most of them just do
`::: rigour.module.name` and let mkdocstrings pull docstrings from
the source. Which means **the docstring is the docs**: there is no
separate hand-written reference.

* Use **Google-style docstrings**: prose intro, then explicit
  `Args:`, `Returns:`, optionally `Raises:` sections.
* Document **every parameter** a public function takes — including
  the obvious ones. The Args section renders as a Parameters table
  in the mkdocs site, and skipped params show as blank rows.
* For classes (including `IntFlag` / `IntEnum`), document members
  under an `Attributes:` section in the class docstring — it renders
  as a named table with descriptions.
* Cross-reference other rigour symbols with **mkdocs-autorefs
  Markdown syntax**: `[Display][full.dotted.path]` or the shorthand
  `[full.dotted.path][]` when you want the name itself as the label.
  Example: `[Normalize][rigour.text.normalize.Normalize]` or just
  `[rigour.text.normalize][]` for a module. Sphinx-style `:class:` /
  `:func:` roles do **not** render here — they come out as literal
  text. The Type column of a Parameters table auto-links type
  annotations without any markup, so description text rarely needs
  an explicit link — plain backticks are fine when you just want
  code formatting.
* Prefer **one canonical reference** per concept. When many functions
  share a parameter with non-obvious semantics (e.g.
  `normalize_flags`, `cleanup`), write the long-form explanation
  once in the owning module's docstring and have individual function
  docstrings just link to it via `:class:` / `:mod:`. This is how
  `rigour.names.org_types` defers to `rigour.text.normalize` for the
  flag vocabulary.
* Verify rendering before landing a docs-affecting change:
  `mkdocs build --strict -f mkdocs.yml` (treats warnings as errors).
  If a new submodule is added, remember to add `::: rigour.my.submodule`
  to the relevant `docs/*.md` — mkdocstrings doesn't auto-recurse.