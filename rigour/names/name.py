"""Name — the top-level object in the `rigour.names` object graph.

Rust-backed via `rigour._core`. The Python-side attribute and method
surface is preserved verbatim:

* `Name(original, form=None, tag=NameTypeTag.UNK, lang=None,
    parts=None, phonetics=True)` — if `parts` is given it is used
  as-is; otherwise `form` (defaulting to `casefold(original)`) is
  tokenised and each token becomes a fresh `NamePart`.
* eager attributes: `original`, `form`, `tag` (mutable), `lang`
  (mutable), `parts`, `spans`, `comparable`, `norm_form`
* dynamic property: `symbols` (recomputed each access from `spans`)
* mutation: `tag_text(text, tag, max_matches=1)`,
  `apply_phrase(phrase, symbol)`, `apply_part(part, symbol)`
* `contains(other)` for PER-aware subset checks
* `Name.consolidate_names(names)` classmethod — drops names that are
  substrings of longer names in the same iterable
* `__hash__` / `__eq__` by `form` (stable across tag mutation)

`parts` is a Python list built once at construction — attribute
reads are zero-copy INCREFs. `spans` starts empty and grows via
`apply_phrase` / `apply_part`.
"""
from rigour._core import Name

__all__ = ["Name"]
