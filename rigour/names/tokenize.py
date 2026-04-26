"""Name tokenisation primitives.

`tokenize_name` is Rust-backed via :func:`rigour._core.tokenize_name`
— one FFI call per invocation, no per-codepoint Python-side
category lookups. `normalize_name` is a small composed convenience
that callers reach for as the cheapest "key for matching" shape.
"""

from functools import lru_cache
from typing import List, Optional


from rigour._core import tokenize_name as _tokenize_name
from rigour.text.normalize import normalize, Normalize
from rigour.util import MEMO_SMALL


def tokenize_name(text: str, token_min_length: int = 1) -> List[str]:
    """Split a person or entity's name into name parts.

    Unicode general-category-aware: separator categories (spaces,
    punctuation, math symbols) split tokens; delete categories
    (combining marks, modifier letters, format chars) drop; letters,
    numbers, and a small set of CJK modifier marks are kept.

    Args:
        text: The name to tokenize.
        token_min_length: Drop tokens shorter than this many
            codepoints. Defaults to 1 (drop only zero-length).

    Returns:
        Tokens in left-to-right order, with any deletion or
        whitespace-substitution applied. Order matches input.
    """
    return _tokenize_name(text, token_min_length)


@lru_cache(maxsize=MEMO_SMALL)
def normalize_name(name: Optional[str]) -> Optional[str]:
    """Casefold and tokenise a name into a stable matching key.

    Convenience composition of :func:`tokenize_name` over a
    casefolded input, rejoined with single ASCII spaces.
    Equivalent to calling
    `normalize(name, Normalize.CASEFOLD | Normalize.NAME)` —
    use that directly when callers want explicit flag control.

    Used internally by the rigour name-matching utilities; not
    intended as a general-purpose public surface.

    Args:
        name: A name string, or `None`.

    Returns:
        Normalised name (lowercase, single-space-separated
        tokens), or `None` if input is `None` or normalises to
        empty.
    """
    if name is None:
        return None
    return normalize(name, Normalize.CASEFOLD | Normalize.NAME)
