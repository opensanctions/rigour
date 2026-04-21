"""NamePart / Span — the leaf classes of the `rigour.names` object graph.

Rust-backed via `rigour._core`. The Python-side attribute and method
surface is preserved verbatim:

* `NamePart(form, index=None, tag=NamePartTag.UNSET, phonetics=True)`
* eager attributes: `form`, `index`, `tag` (mutable), `latinize`,
  `numeric`, `ascii`, `integer`, `comparable`, `metaphone`
* `can_match(other)` delegates to `NamePartTag.can_match`
* `__hash__` / `__eq__` by the precomputed `_hash` (tuple of
  `(index, form)`)
* `Span(parts, symbol)` with precomputed `comparable`

`phonetics=False` at construction skips the metaphone computation —
`part.metaphone` is `None` in that case. `ascii` uses
`rigour._core.maybe_ascii` (narrow 6-script transliteration) instead
of the pre-port `normality.ascii_text`; parts whose form is not in
`LATINIZE_SCRIPTS` now resolve `ascii` to `None` rather than a
PyICU-transliterated approximation.
"""
from rigour._core import NamePart, Span

__all__ = ["NamePart", "Span"]
