"""Name tokenisation primitives.

`tokenize_name` is Rust-backed via :func:`rigour._core.tokenize_name`
— one FFI call per invocation, no per-codepoint Python-side
category lookups. `normalize_name` remains as a Python wrapper
(deprecated) that composes `tokenize_name` with `str.casefold`.
"""

import warnings
from functools import lru_cache
from typing import List, Optional

from normality.constants import WS

from rigour._core import tokenize_name as _tokenize_name
from rigour.util import MEMO_TINY


def tokenize_name(text: str, token_min_length: int = 1) -> List[str]:
    """Split a person or entity's name into name parts.

    Unicode general-category-aware: separator categories (spaces,
    punctuation, math symbols) split tokens; delete categories
    (combining marks, modifier letters, format chars) drop; letters,
    numbers, and a small set of CJK modifier marks are kept.
    """
    return _tokenize_name(text, token_min_length)


def prenormalize_name(name: Optional[str]) -> str:
    """Prepare a name for tokenization and matching."""
    if name is None:
        return ""
    return name.casefold()


def normalize_name(name: Optional[str], sep: str = WS) -> Optional[str]:
    """Normalize a name for tokenization and matching.

    .. deprecated::
        This convenience wrapper is slated for removal. Compose
        :func:`tokenize_name` with :meth:`str.casefold` directly, or
        reach for one of the :mod:`rigour.text.normalize` primitives
        if you need a different normalisation shape.
    """
    warnings.warn(
        "rigour.names.normalize_name is deprecated; compose "
        "tokenize_name with str.casefold directly, or use "
        "rigour.text.normalize primitives.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _normalize_name(name, sep)


@lru_cache(maxsize=MEMO_TINY)
def _normalize_name(name: Optional[str], sep: str = WS) -> Optional[str]:
    # Cached inner implementation. The public `normalize_name`
    # wrapper emits DeprecationWarning on every call; without this
    # split the cache would swallow the warning after the first hit
    # per unique input.
    if name is None:
        return None
    joined = sep.join(tokenize_name(prenormalize_name(name)))
    if len(joined) == 0:
        return None
    return joined
