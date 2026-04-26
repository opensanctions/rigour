"""Name tokenisation primitives.

`tokenize_name` is Rust-backed via :func:`rigour._core.tokenize_name`
— one FFI call per invocation, no per-codepoint Python-side
category lookups. `normalize_name` remains as a Python wrapper
(deprecated) that composes `tokenize_name` with `str.casefold`.
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
        text (str): The name to tokenize.
        token_min_length (int): Minimum length of tokens to keep.

    Returns:
        List[str]: A list of name tokens.
    """
    return _tokenize_name(text, token_min_length)


@lru_cache(maxsize=MEMO_SMALL)
def normalize_name(name: Optional[str]) -> Optional[str]:
    """Normalize a name for tokenization and matching. This is used internally by
    utility functions, but should not be picked up by external callers.

    Args:
        name (Optional[str]): The name to normalize.

    Returns:
        Optional[str]: The normalized name, or None if the input is None or empty.
    """
    if name is None:
        return None
    return normalize(name, Normalize.CASEFOLD | Normalize.NAME)
