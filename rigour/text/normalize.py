"""Flag-based text normalization.

Replaces the `normalizer: Callable[[Optional[str]], Optional[str]]`
callback pattern inherited from normality. See `plans/rust-normalizer.md`
for the design rationale. The actual work runs in Rust via
`rigour._core._normalize`; this module provides the idiomatic Python
surface (`IntFlag` / `IntEnum`).

Pipeline order, independent of bit order:

    1. STRIP                — trim leading/trailing whitespace
    2. NFKD / NFKC / NFC    — at most one is meaningful
    3. CASEFOLD             — Unicode full casefold (ß → ss)
    4. ASCII or LATINIZE    — ASCII wins if both set
    5. Cleanup              — category_replace, unless Cleanup.Noop
    6. SQUASH_SPACES        — collapse whitespace runs, trim ends

Empty output → None.
"""
from enum import IntEnum, IntFlag
from typing import Optional

from rigour._core import _normalize

__all__ = ["normalize", "Normalize", "Cleanup"]


class Normalize(IntFlag):
    # Bit values MUST match rust/src/text/normalize.rs `bitflags! Normalize`.
    STRIP = 1 << 0
    SQUASH_SPACES = 1 << 1
    CASEFOLD = 1 << 2
    NFC = 1 << 3
    NFKC = 1 << 4
    NFKD = 1 << 5
    LATINIZE = 1 << 6
    ASCII = 1 << 7


class Cleanup(IntEnum):
    # Values MUST match the tag encoding in rust/src/lib.rs py_normalize().
    Noop = 0
    Strong = 1
    Slug = 2


def normalize(
    text: Optional[str],
    flags: Normalize = Normalize(0),
    cleanup: Cleanup = Cleanup.Noop,
) -> Optional[str]:
    """Apply a sequence of normalization steps selected by `flags` and
    `cleanup`. See the module docstring for pipeline order.

    Returns None if `text` is None, or if the output is empty after all
    steps run.
    """
    if text is None:
        return None
    return _normalize(text, int(flags), int(cleanup))
