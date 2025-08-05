"""
This module provides a set of classes and functions to work with countries, territories and
jurisdictions. It is based on the notion that a territory is any political entity that may
be referred to by a code, such as a country, a territory or a jurisdiction. Jurisdictions are
most countries, but also sub-national entities like states, especially if they have their own
legal incorporation regime.

For all territories, mappings to Wikidata QIDs are provided, as well as a set of other codes
that may be used to refer to the same territory. The module also provides a set of functions
to retrieve territories by their codes or QIDs.
"""

from functools import cache
from typing import List, Optional
from rigour.territories.territory import Territory
from rigour.territories.territory import get_index as _get_index
from rigour.territories.lookup import lookup_by_identifier, lookup_territory
from rigour.territories.util import clean_code


__all__ = [
    "get_territory",
    "get_territories",
    "get_territory_by_qid",
    "get_ftm_countries",
    "lookup_by_identifier",
    "lookup_territory",
]


def get_territory(code: str) -> Optional[Territory]:
    """Get a territory object for the given code.

    Args:
        code: Country, territory or jurisdiction code.

    Returns:
        A territory object.
    """
    index = _get_index()
    code = clean_code(code)
    return index.get(code)


@cache
def get_territories() -> List[Territory]:
    """Get all the territories in the index.

    Returns:
        A list of territories.
    """
    return sorted(set(_get_index().values()))


@cache
def get_territory_by_qid(qid: str) -> Optional[Territory]:
    """Get a territory object for the given Wikidata QID.

    Args:
        qid: Wikidata QID.

    Returns:
        A territory object.
    """
    for territory in _get_index().values():
        if qid in territory.qids:
            return territory
    return None


def get_ftm_countries() -> List[Territory]:
    """Get all the countries that were supported by the FtM `country`
    property type.

    Returns:
        A list of territories.
    """
    territories: List[Territory] = []
    for territory in get_territories():
        if territory.is_ftm:
            territories.append(territory)
    return territories
