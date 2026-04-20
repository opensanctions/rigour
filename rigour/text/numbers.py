"""Numeric string parsing with Unicode digit / Roman / fraction / CJK
support.

Rust-backed via :func:`rigour._core.string_number`. See the header of
``rust/src/text/numbers.rs`` for the coverage and multi-character rules.
"""

# TODO: if this is only used on name parts, do we need to expose it?
from rigour._core import string_number

__all__ = ["string_number"]
