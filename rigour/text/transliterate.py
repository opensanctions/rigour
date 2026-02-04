"""Text transliteration utilities.

This module provides functions to transliterate text between scripts,
particularly to ASCII for normalization and matching purposes.

The implementation uses ICU (International Components for Unicode) via
the Rust binding for performance, matching the behavior of the normality
library.
"""

from typing import Optional

from rigour._core import ascii_text as _ascii_text_core


def ascii_text(text: Optional[str]) -> str:
    """Transliterate text to ASCII.

    This function converts text from any script to ASCII using ICU
    transliteration. It applies the following transformations:
    1. Transliterate to Latin script (Any-Latin)
    2. Decompose to NFKD
    3. Remove non-spacing marks
    4. Remove accents
    5. Remove symbols
    6. Convert to Latin-ASCII

    This matches the behavior of normality.ascii_text().

    Args:
        text: The text to transliterate. If None, returns empty string.

    Returns:
        ASCII-only string. Returns empty string for None or empty input.

    Examples:
        >>> ascii_text("Café")
        'Cafe'
        >>> ascii_text("Порошенко Петро")
        'Porosenko Petro'
        >>> ascii_text("əhməd")
        'ahmad'
        >>> ascii_text("Häschen Spaß")
        'Haschen Spass'
        >>> ascii_text(None)
        ''
        >>> ascii_text("")
        ''

    Note:
        This function is implemented in Rust for performance. The underlying
        implementation uses ICU transliteration to ensure accurate conversion
        across all Unicode scripts.
    """
    if text is None or text == "":
        return ""

    return _ascii_text_core(text)


__all__ = ["ascii_text"]
