"""
Name handling utilities for person and organisation names. This module contains a large (and growing)
set of tools for handling names. In general, there are three types of names: people, organizations,
and objects. Different normalization may be required for each of these types, including prefix removal
for person names (e.g. "Mr." or "Ms.") and type normalization for organization names (e.g.
"Incorporated" -> "Inc" or "Limited" -> "Ltd").

The `Name` class is meant to provide a structure for a name, including its original form, normalized form,
metadata on the type of thing described by the name, and the language of the name. The `NamePart` class
is used to represent individual parts of a name, such as the first name, middle name, and last name.

* [Falsehoods Programmers Believe About Names](https://www.kalzumeus.com/2010/06/17/falsehoods-programmers-believe-about-names/)
"""

from rigour.names.name import Name
from rigour.names.part import NamePart
from rigour.names.tag import NamePartTag, NameTypeTag
from rigour.names.pick import pick_name, pick_case
from rigour.names.check import is_name
from rigour.names.tokenize import tokenize_name
from rigour.names.person import remove_person_prefixes
from rigour.names.org_types import replace_org_types_display
from rigour.names.org_types import replace_org_types_compare
from rigour.names.org_types import extract_org_types, remove_org_types

__all__ = [
    "pick_name",
    "pick_case",
    "tokenize_name",
    "is_name",
    "Name",
    "NamePart",
    "NamePartTag",
    "NameTypeTag",
    "remove_person_prefixes",
    "replace_org_types_display",
    "replace_org_types_compare",
    "extract_org_types",
    "remove_org_types",
]
