"""
#### Organization and Company Types Database

This module provides functionality to normalize and replace organization types - such as company
legal forms - in an entity name. The objective is to standardize the representation of these types
and to facilitate name matching on organizations and companies.
"""

import yaml
import logging
from functools import cache
from normality import collapse_spaces
from typing import Dict, List, Optional, TypedDict

from rigour.data import DATA_PATH
from rigour.text.dictionary import Normalizer, Replacer

log = logging.getLogger(__name__)


class OrgTypeSpec(TypedDict):
    display: str
    compare: str
    aliases: List[str]


def read_org_types() -> List[OrgTypeSpec]:
    """Read the organization types database."""
    path = DATA_PATH / "names" / "org_types.yml"
    with open(path, "r") as fh:
        data: Dict[str, List[OrgTypeSpec]] = yaml.safe_load(fh)
    return data["types"]


def _normalize_display(text: Optional[str]) -> Optional[str]:
    """Normalize the display name for the organization type."""
    return collapse_spaces(text)


@cache
def get_display_replacer(normalizer: Normalizer = _normalize_display) -> Replacer:
    """Get a replacer for the display names of organization types."""
    mapping: Dict[str, str] = {}
    for org_type in read_org_types():
        display_norm = normalizer(org_type.get("display"))
        if display_norm is None:
            continue
        for alias in org_type["aliases"]:
            alias_norm = normalizer(alias)
            if alias_norm is None or alias_norm == display_norm:
                continue
            if alias_norm in mapping and mapping[alias_norm] != display_norm:
                log.warning("Duplicate alias: %r (for %r)", alias_norm, display_norm)
            mapping[alias_norm] = display_norm
    return Replacer(mapping, ignore_case=True)


def replace_org_types_display(
    text: str, normalizer: Normalizer = _normalize_display
) -> str:
    """Replace organization types in the text with their shortened form. This will perform
    a display-safe (light) form of normalization, useful for shortening spelt-out legal forms
    into common abbreviations (eg. Siemens Aktiengesellschaft -> Siemens AG).

    If the result of the replacement yields an empty string, the original text is returned as-is.

    Args:
        text (str): The text to be processed.

    Returns:
        Optional[str]: The text with organization types replaced.
    """
    normalized = normalizer(text)
    if normalized is None:
        return text
    is_uppercase = normalized.isupper()
    replacer = get_display_replacer(normalizer=normalizer)
    out_text = replacer(text)
    if out_text is None:
        return text
    if is_uppercase:
        out_text = out_text.upper()
    return out_text
