"""
Name handling utilities for person and organisation names.
"""

from rigour.names.pick import pick_name, pick_case
from rigour.names.part import name_parts
from rigour.names.check import is_name
from rigour.names.tokenize import tokenize_name

__all__ = ["pick_name", "pick_case", "name_parts", "is_name", "tokenize_name"]
