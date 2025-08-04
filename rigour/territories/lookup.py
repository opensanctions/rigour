import logging
from functools import cache
from typing import Dict, Optional

from rigour.territories.territory import Territory
from rigour.territories.territory import get_index as _get_index
from rigour.territories.util import clean_code, normalize_territory_name

log = logging.getLogger(__name__)


@cache
def _get_identifier_map() -> Dict[str, Territory]:
    """Create a mapping of territory codes and names to Territory objects."""
    index = _get_index()
    mapping: Dict[str, Territory] = {}

    for territory in index.values():
        mapping[territory.code] = territory
        if territory.alpha3:
            mapping[territory.alpha3] = territory
        for code in territory.other_codes:
            mapping[code] = territory
        if territory.qid:
            qid = clean_code(territory.qid)
            mapping[qid] = territory
        for qid in territory.other_qids:
            qid_cleaned = clean_code(qid)
            mapping[qid_cleaned] = territory
    return mapping


def lookup_by_identifier(identifier: str) -> Optional[Territory]:
    """Lookup a territory by its identifier, which can be a 2- or 3-letter code, or QID.

    Args:
        identifier: The identifier to lookup.

    Returns:
        An instance of Territory if found, otherwise None.
    """
    mapping = _get_identifier_map()
    identifier = clean_code(identifier)
    return mapping.get(identifier)


@cache
def _get_territory_names() -> Dict[str, Territory]:
    """Get a mapping of strong names to Territory objects."""
    index = _get_index()
    mapping: Dict[str, Territory] = {}
    for territory in index.values():
        names = list(territory.names_strong)
        names.append(territory.name)
        names.append(territory.full_name)
        for name in names:
            nname = normalize_territory_name(name)
            if nname in mapping and mapping[nname] != territory:
                log.warning(
                    "Duplicate strong name found: %r for %s and %s",
                    name,
                    mapping.get(nname, territory).name,
                    territory.name,
                )
            mapping[nname] = territory

    weak_mapping: Dict[str, Territory] = {}
    for territory in index.values():
        for name in territory.names_weak:
            nname = normalize_territory_name(name)
            if nname in mapping:
                continue
            if nname in weak_mapping and weak_mapping[nname] != territory:
                log.warning(
                    "Duplicate weak name found: %r for %s and %s",
                    name,
                    weak_mapping.get(nname, territory).name,
                    territory.name,
                )
            weak_mapping[nname] = territory
    mapping.update(weak_mapping)
    return mapping


def lookup_territory(text: str) -> Optional[Territory]:
    """Lookup a territory by various codes and names.

    Args:
        text: The text to lookup, which can be a code, name, or other identifier.

    Returns:
        An instance of Territory if found, otherwise None.
    """
    territory = lookup_by_identifier(text)
    if territory is not None:
        return territory
    normalized_name = normalize_territory_name(text)
    names = _get_territory_names()
    return names.get(normalized_name)
