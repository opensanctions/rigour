This library contains data validation and cleaning routines that are meant to be precise. These methods are supported by resource data. The resource data is derived from real-world datasets and meant to cover common cases of data variations in corporate registries, and AML/KYC screening data.

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