"""
Name handling utilities for person and organisation names.
"""

from rigour.names.pick import pick_name
from rigour.names.name import Name
from rigour.names.part import NamePart
from rigour.names.tag import NamePartTag, NameTypeTag
from rigour.names.pick import pick_name, pick_case
from rigour.names.check import is_name
from rigour.names.tokenize import tokenize_name


__all__ = [
    "pick_name",
    "pick_case",
    "tokenize_name",
    "is_name",
    "Name",
    "NamePart",
    "NamePartTag",
    "NameTypeTag",
]
