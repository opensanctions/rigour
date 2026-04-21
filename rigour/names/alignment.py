"""Align the name parts of two person names so that corresponding
tokens end up at the same output index — used by the matcher before
running a per-index similarity pass across the two sides.

Rust-backed via `rigour._core.align_person_name_order`; see
`plans/rust-alignment.md` for the requirements spec and the full
test-case map at `tests/names/test_alignment.py`.
"""
from rigour._core import align_person_name_order

__all__ = ["align_person_name_order"]
