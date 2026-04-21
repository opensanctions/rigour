"""Align the name parts of two person names so corresponding tokens
end up at the same output index.

Used by the name matcher to line up comparable tokens before running
a per-index similarity pass across the two sides — without it, a pair
like ``["Doe", "John"]`` vs ``["John", "Doe"]`` would compare
mismatched positions and score poorly despite being the same name.
"""
from rigour._core import align_person_name_order

__all__ = ["align_person_name_order"]
