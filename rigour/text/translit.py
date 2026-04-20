"""Opportunistic transliteration: `should_ascii` + `maybe_ascii`.

The minimal transliteration surface rigour exposes going forward.
Covers only the scripts listed in `rigour.text.scripts.LATINIZE_SCRIPTS`
(Latin, Cyrillic, Greek, Armenian, Georgian, Hangul). Anything
outside that set passes through unchanged (default) or becomes
empty (``drop=True``).

For broader-script, lossy transliteration (Han, Arabic, Devanagari,
etc.) use `normality.ascii_text` / `normality.latinize_text` —
rigour deliberately does not try to duplicate that surface.

See `plans/rust-minimal-translit.md` for the scope rationale.
"""

from rigour._core import maybe_ascii as maybe_ascii
from rigour._core import should_ascii as should_ascii

__all__ = ["should_ascii", "maybe_ascii"]
