"""Name — the top-level object in the `rigour.names` object graph.

Rust-backed via `rigour._core`. Python-side surface:

* `Name(original, form=None, tag=NameTypeTag.UNK, phonetics=True)` —
  `form` defaults to `casefold(original)` and is tokenised; each
  token becomes a fresh `NamePart`.
* eager attributes: `original`, `form`, `tag` (mutable), `parts`,
  `spans`, `comparable`, `norm_form`
* dynamic property: `symbols` (recomputed each access from `spans`)
* mutation: `tag_text(text, tag, max_matches=1)`,
  `apply_phrase(phrase, symbol)`, `apply_part(part, symbol)`
* `contains(other)` for PER-aware subset checks
* `Name.consolidate_names(names)` classmethod — drops names that are
  substrings of longer names in the same iterable
* `__hash__` / `__eq__` by `form` (stable across tag mutation)

`parts` is a tuple built once at construction — attribute reads are
zero-copy INCREFs. `spans` starts empty and grows via `apply_phrase`
/ `apply_part`.
"""
from rigour._core import Name

__all__ = ["Name"]
