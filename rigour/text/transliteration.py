from functools import lru_cache

from rigour._core import ascii_text as _ascii_text
from rigour._core import latinize_text as _latinize_text
from rigour.util import MEMO_LARGE

__all__ = ["ascii_text", "latinize_text"]


# No non-Latin characters live below this codepoint. Used as an inexpensive
# Python-side fast path for `latinize_text` to skip FFI for pure-Latin inputs.
_LATIN_BLOCK = 740


@lru_cache(maxsize=MEMO_LARGE)
def ascii_text(text: str) -> str:
    """Transliterate text to ASCII.

    Runs the per-script ICU4X transliterators (for Cyrillic, Arabic, Greek,
    Han, Hangul, Georgian, Armenian, Devanagari, Katakana, Hiragana, Hebrew),
    NFKD-decomposes the result, strips nonspacing marks, then applies a small
    fallback table for non-decomposable diacritics (ø → o, ß → ss, etc.).

    Returns the input unchanged if it's already ASCII (avoids the FFI crossing
    entirely).
    """
    if text.isascii():
        return text
    return _ascii_text(text)


@lru_cache(maxsize=MEMO_LARGE)
def latinize_text(text: str) -> str:
    """Transliterate text to Latin script, preserving diacritics.

    Applies per-script ICU4X transliterators until everything's in Latin; does
    not strip diacritics or apply the ASCII fallback table (use ``ascii_text``
    for that).

    Returns the input unchanged if it's already within the Latin-and-below
    codepoint block (`< U+02E4`).
    """
    if all(ord(c) < _LATIN_BLOCK for c in text):
        return text
    return _latinize_text(text)
