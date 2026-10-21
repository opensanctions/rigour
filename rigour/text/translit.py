"""Opportunistic transliteration: `should_ascii` + `maybe_ascii`.

The minimal transliteration surface rigour exposes going forward.
Covers only six admitted scripts (Latin, Cyrillic, Greek, Armenian,
Georgian, Hangul); the admission policy is defined in the Rust core.
Anything outside that set passes through unchanged (default) or
becomes empty (``drop=True``).

For broader-script, lossy transliteration (Han, Arabic, Devanagari,
etc.) use [ascii_text][rigour.text.translit.ascii_text], which falls
back to `normality.ascii_text` for whatever `maybe_ascii` leaves
non-ASCII.
"""

import normality

from rigour._core import maybe_ascii as maybe_ascii
from rigour._core import should_ascii as should_ascii

__all__ = ["ascii_text", "maybe_ascii", "should_ascii"]


def ascii_text(text: str) -> str:
    """Transliterate text in any script to ASCII.

    Use this instead of `normality.ascii_text` so that ASCII keys agree with
    `NamePart.ascii` and other `maybe_ascii` output: text in the admitted
    scripts gets rigour's spellings (`Шевченко → Shevchenko`, not
    `Sevcenko`). Whatever `maybe_ascii` leaves non-ASCII, such as other
    scripts or symbols, goes through `normality.ascii_text`. A string that
    mixes an admitted script with another one is transliterated entirely by
    `normality`.

    Args:
        text: The text to transliterate.

    Returns:
        The ASCII transliteration.
    """
    out = maybe_ascii(text)
    if out.isascii():
        return out
    return normality.ascii_text(out)
