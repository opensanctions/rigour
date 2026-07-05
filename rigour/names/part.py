"""NamePart / Span — the leaf classes of the `rigour.names` object graph.

Rust-backed via `rigour._core`. Python-side surface:

* `NamePart(form, index, tag=NamePartTag.UNSET, phonetics=True)` —
  `index` is the part's position within its name and is required.
* eager attributes: `form`, `index`, `tag` (mutable), `latinize`,
  `numeric`, `ascii`, `integer`, `comparable`, `metaphone`
* `NamePart.tag_sort(parts)` classmethod — stable-sort parts into
  human display order by tag (honorifics, given, middle, family, …)
* tag compatibility checks live on the tag: `part.tag.can_match(other.tag)`
* `__hash__` / `__eq__` by the precomputed `_hash` (tuple of
  `(index, form)`)
* `Span(parts, symbol)` with precomputed `comparable`

`phonetics=False` at construction skips the metaphone computation —
`part.metaphone` is `None` in that case. `ascii` uses
`rigour._core.maybe_ascii` (narrow 6-script transliteration); parts
whose form is outside the admitted scripts resolve `ascii` to `None`.
"""
from rigour._core import NamePart, Span

__all__ = ["NamePart", "Span"]
