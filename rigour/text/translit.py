"""Opportunistic transliteration: `should_ascii` + `maybe_ascii`.

The minimal transliteration surface rigour exposes going forward.
Covers only six admitted scripts (Latin, Cyrillic, Greek, Armenian,
Georgian, Hangul); the admission policy is defined in the Rust core.
Anything outside that set passes through unchanged (default) or
becomes empty (``drop=True``).

For broader-script, lossy transliteration (Han, Arabic, Devanagari,
etc.) use `normality.ascii_text` / `normality.latinize_text` —
rigour deliberately does not try to duplicate that surface.
"""

from rigour._core import maybe_ascii as maybe_ascii
from rigour._core import should_ascii as should_ascii

__all__ = ["should_ascii", "maybe_ascii"]
