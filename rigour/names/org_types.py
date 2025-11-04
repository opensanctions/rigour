"""
#### Organization and Company Types Database

This module provides functionality to normalize and replace organization types - such as company
legal forms - in an entity name. The objective is to standardize the representation of these types
and to facilitate name matching on organizations and companies.

This previous existed as part of `fingerprints` library. The implementation in `rigour` tries to
make a clearer separation between other string cleaning a user may want to perform on a company name
(eg. romanisation) and the company type detection logic. This module only handles the latter.

Please improve this by adding more organization types to the database located here:

* [org_types.yml](https://github.com/opensanctions/rigour/blob/main/resources/names/org_types.yml)

The database is originally based on three different sources:

* A [Google Spreadsheet](https://docs.google.com/spreadsheets/d/1Cw2xQ3hcZOAgnnzejlY5Sv3OeMxKePTqcRhXQU8rCAw/edit?ts=5e7754cf#gid=0)
  created by OCCRP.
* The ISO 20275: [Entity Legal Forms Code List](https://www.gleif.org/en/about-lei/code-lists/iso-20275-entity-legal-forms-code-list)
* Wikipedia maintains an index of [types of business entity](https://en.wikipedia.org/wiki/Types_of_business_entity).

"""

import sys
import logging
from functools import cache, lru_cache
from normality import squash_spaces
from typing import Dict, List, Optional, Set, Tuple

from rigour.text.dictionary import Normalizer, Replacer
from rigour.util import resource_lock, unload_module

log = logging.getLogger(__name__)


def normalize_display(text: Optional[str]) -> Optional[str]:
    """Normalize the display name for the organization type."""
    if text is None:
        return None
    text = squash_spaces(text)
    if len(text) == 0:
        return None
    return text


def _normalize_compare(text: Optional[str]) -> Optional[str]:
    """Stub normalizer for more heavy string cleanup."""
    if text is None:
        return None
    norm = squash_spaces(text)
    if len(norm) == 0:
        return None
    return norm.casefold()


@cache
def _display_replacer(normalizer: Normalizer = normalize_display) -> Replacer:
    """Get a replacer for the display names of organization types."""
    from rigour.data.names.org_types import ORG_TYPES

    mapping: Dict[str, str] = {}
    clashes: Set[str] = set()
    for org_type in ORG_TYPES:
        display_norm = normalizer(org_type.get("display"))
        if display_norm is None:
            continue
        for alias in org_type.get("aliases", []):
            alias_norm = normalizer(alias)
            if alias_norm is None or len(alias_norm.strip()) == 0:
                continue
            if alias_norm == display_norm:
                continue
            if alias_norm in mapping and mapping[alias_norm] != display_norm:
                log.warning(
                    "Duplicate alias: %r (for %r, and %r)",
                    alias_norm,
                    display_norm,
                    mapping[alias_norm],
                )  # pragma: no cover
                clashes.add(alias_norm)
            mapping[alias_norm] = display_norm
    for alias in clashes:
        mapping.pop(alias, None)

    unload_module("rigour.data.names.org_types")
    return Replacer(mapping, ignore_case=True)


def replace_org_types_display(
    name: str, normalizer: Normalizer = normalize_display
) -> str:
    """Replace organization types in the text with their shortened form. This will perform
    a display-safe (light) form of normalization, useful for shortening spelt-out legal forms
    into common abbreviations (eg. Siemens Aktiengesellschaft -> Siemens AG).

    If the result of the replacement yields an empty string, the original text is returned as-is.

    Args:
        name (str): The text to be processed. It is assumed to be already normalized (see below).
        normalizer (Callable[[str | None], str | None]): A text normalization function to run on the
            lookup values before matching to remove text anomalies and make matches more likely.

    Returns:
        Optional[str]: The text with organization types replaced.
    """
    is_uppercase = name.isupper()
    with resource_lock:
        replacer = _display_replacer(normalizer=normalizer)
        out_text = replacer(name)
    if out_text is None:
        return name
    if is_uppercase:
        out_text = out_text.upper()
    return out_text


@cache
def _compare_replacer(normalizer: Normalizer = _normalize_compare) -> Replacer:
    """Get a replacer for the display names of organization types."""
    from rigour.data.names.org_types import ORG_TYPES

    mapping: Dict[str, str] = {}
    for org_type in ORG_TYPES:
        display_form = normalizer(org_type.get("display"))
        compare_form = org_type.get("compare", display_form)
        # Allow for empty compare forms, which are used to indicate that the
        # organization type be removed before comparison:
        compare_norm = (
            normalizer(compare_form)
            if compare_form is None or len(compare_form) > 0
            else ""
        )
        if compare_norm is None:
            continue
        compare_norm = sys.intern(compare_norm)
        for alias in org_type.get("aliases", []):
            alias_norm = normalizer(alias)
            if alias_norm is None:
                continue
            if alias_norm in mapping and mapping[alias_norm] != compare_norm:
                log.warning(
                    "Duplicate alias: %r (for %r, and %r)",
                    alias_norm,
                    compare_norm,
                    mapping[alias_norm],
                )  # pragma: no cover
            mapping[alias_norm] = compare_norm

        display_norm = normalizer(display_form)
        if display_norm is not None and display_norm not in mapping:
            mapping[display_norm] = compare_norm

    unload_module("rigour.data.names.org_types")
    return Replacer(mapping, ignore_case=True)


@cache
def _generic_replacer(normalizer: Normalizer = _normalize_compare) -> Replacer:
    """Get a replacer for the names of organization types, mapping them to generic types like LLC, JSC."""
    from rigour.data.names.org_types import ORG_TYPES

    mapping: Dict[str, str] = {}
    for org_type in ORG_TYPES:
        generic_norm = normalizer(org_type.get("generic"))
        if generic_norm is None:
            continue
        generic_norm = sys.intern(generic_norm)
        for alias in org_type.get("aliases", []):
            alias_norm = normalizer(alias)
            if alias_norm is None:
                continue
            if alias_norm in mapping and mapping[alias_norm] != generic_norm:
                log.warning(
                    "Duplicate alias: %r (for %r, and %r)",
                    alias_norm,
                    generic_norm,
                    mapping[alias_norm],
                )  # pragma: no cover
            mapping[alias_norm] = generic_norm

        display_norm = normalizer(org_type.get("display"))
        if display_norm is not None and display_norm not in mapping:
            mapping[display_norm] = generic_norm

    unload_module("rigour.data.names.org_types")
    return Replacer(mapping, ignore_case=True)


@lru_cache(maxsize=1024)
def replace_org_types_compare(
    name: str, normalizer: Normalizer = _normalize_compare, generic: bool = False
) -> str:
    """Replace any organization type indicated in the given entity name (often as a prefix or suffix)
    with a heavily normalized form label. This will re-write country-specific entity types (eg. GmbH)
    into a simplified spelling suitable for comparison using string distance. The resulting text is
    meant to be used in comparison processes, but no longer fit for presentation to a user.

    Args:
        name (str): The text to be processed. It is assumed to be already normalized (see below).
        normalizer (Callable[[str | None], str | None]): A text normalization function to run on the
            lookup values before matching to remove text anomalies and make matches more likely.
        generic (bool): If True, return the generic form of the organization type (e.g. LLC, JSC) instead
            of the type-specific comparison form (GmbH, AB, NV).

    Returns:
        Optional[str]: The text with organization types replaced.
    """
    with resource_lock:
        _func = _generic_replacer if generic else _compare_replacer
        replacer = _func(normalizer=normalizer)
    return replacer(name) or name


def extract_org_types(
    name: str, normalizer: Normalizer = _normalize_compare, generic: bool = False
) -> List[Tuple[str, str]]:
    """Match any organization type designation (e.g. LLC, Inc, GmbH) in the given entity name and
    return the extracted type.

    This can be used as a very poor man's method to determine if a given string is a company name.

    Args:
        name (str): The text to be processed. It is assumed to be already normalized (see below).
        normalizer (Callable[[str | None], str | None]): A text normalization function to run on the
            lookup values before matching to remove text anomalies and make matches more likely.
        generic (bool): If True, return the generic form of the organization type (e.g. LLC, JSC) instead
            of the type-specific comparison form (GmbH, AB, NV).

    Returns:
        Tuple[str, str]: Tuple of the org type as matched, and the compare form of it.
    """
    with resource_lock:
        _func = _generic_replacer if generic else _compare_replacer
        replacer = _func(normalizer=normalizer)
    matches: List[Tuple[str, str]] = []
    for matched in replacer.extract(name):
        matches.append((matched, replacer.mapping.get(matched, matched)))
    return matches


def remove_org_types(
    name: str, replacement: str = "", normalizer: Normalizer = _normalize_compare
) -> str:
    """Match any organization type designation (e.g. LLC, Inc, GmbH) in the given entity name and
    replace it with the given fixed string (empty by default, which signals removal).

    Args:
        name (str): The text to be processed. It is assumed to be already normalized (see below).
        normalizer (Callable[[str | None], str | None]): A text normalization function to run on the
            lookup values before matching to remove text anomalies and make matches more likely.

    Returns:
        str: The text with organization types replaced/removed.
    """
    with resource_lock:
        replacer = _compare_replacer(normalizer=normalizer)
    return replacer.remove(name, replacement=replacement)
