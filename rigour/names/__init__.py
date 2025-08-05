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
from rigour.names.symbol import Symbol
from rigour.names.part import NamePart, Span
from rigour.names.tag import NamePartTag, NameTypeTag
from rigour.names.pick import pick_name, pick_case, reduce_names
from rigour.names.check import is_name, is_stopword
from rigour.names.tokenize import tokenize_name, prenormalize_name, normalize_name
from rigour.names.person import load_person_names, load_person_names_mapping
from rigour.names.prefix import remove_person_prefixes, remove_org_prefixes
from rigour.names.prefix import remove_obj_prefixes
from rigour.names.tagging import tag_person_name, tag_org_name
from rigour.names.org_types import replace_org_types_display
from rigour.names.org_types import replace_org_types_compare
from rigour.names.org_types import extract_org_types, remove_org_types
from rigour.names.alignment import align_person_name_order

__all__ = [
    "pick_name",
    "pick_case",
    "reduce_names",
    "tokenize_name",
    "prenormalize_name",
    "normalize_name",
    "is_name",
    "is_stopword",
    "Name",
    "Symbol",
    "Span",
    "NamePart",
    "NamePartTag",
    "NameTypeTag",
    "remove_person_prefixes",
    "remove_org_prefixes",
    "remove_obj_prefixes",
    "load_person_names",
    "load_person_names_mapping",
    "replace_org_types_display",
    "replace_org_types_compare",
    "align_person_name_order",
    "extract_org_types",
    "remove_org_types",
    "tag_person_name",
    "tag_org_name",
]
