"""
Name handling utilities for person and organisation names. This module contains a large (and growing)
set of tools for handling names. In general, there are three types of names: people, organizations,
and objects. Different normalization may be required for each of these types, including prefix removal
for person names (e.g. "Mr." or "Ms.") and type normalization for organization names (e.g.
"Incorporated" -> "Inc" or "Limited" -> "Ltd").

The `Name` class is meant to provide a structure for a name, including its original form, normalized form,
metadata on the type of thing described by the name, and the language of the name. The `NamePart` class
is used to represent individual parts of a name, such as the first name, middle name, and last name.
"""

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
