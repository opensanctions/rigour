import logging
from functools import cache, lru_cache
from rapidfuzz.distance import Levenshtein
from typing import Dict, List, Optional

from rigour.data import read_jsonl
from rigour.territories.territory import Territory
from rigour.territories.territory import TERRITORIES_FILE, get_index as _get_index
from rigour.territories.util import clean_code, normalize_territory_name
from rigour.util import MEMO_MEDIUM, resource_lock

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
        if territory.qid:  # pragma: no cover
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
    """Get a mapping of names to Territory objects."""
    index = _get_index()
    mapping: Dict[str, Territory] = {}
    weaks: Dict[Territory, List[str]] = {}
    for data in read_jsonl(TERRITORIES_FILE):
        code = data["code"]
        territory = index.get(code)
        if territory is None:  # pragma: no cover
            raise RuntimeError(f"Missing territory for code: {code}")
        names: List[str] = data.get("names_strong", [])
        weaks[territory] = data.get("names_weak", [])
        names.append(territory.name)
        names.append(territory.full_name)
        for name in names:
            nname = normalize_territory_name(name)
            if nname in mapping and mapping[nname] != territory:  # pragma: no cover
                log.warning(
                    "Duplicate strong name found: %r for %s and %s",
                    name,
                    mapping.get(nname, territory).name,
                    territory.name,
                )
            mapping[nname] = territory

    weak_mapping: Dict[str, Territory] = {}
    for territory, names_weak in weaks.items():
        for name in names_weak:
            nname = normalize_territory_name(name)
            if nname in mapping:
                continue
            if (
                nname in weak_mapping and weak_mapping[nname] != territory
            ):  # pragma: no cover
                log.warning(
                    "Duplicate weak name found: %r for %s and %s",
                    name,
                    weak_mapping.get(nname, territory).name,
                    territory.name,
                )
            weak_mapping[nname] = territory
    mapping.update(weak_mapping)
    return mapping


def _fuzzy_search(name: str) -> Optional[Territory]:
    best_territory: Optional[Territory] = None
    cutoff = int(len(name) * 0.3)
    best_distance = cutoff + 1
    with resource_lock:
        names = _get_territory_names()
    for cand, territory in names.items():
        if len(cand) <= 4:
            continue
        distance = Levenshtein.distance(name, cand, score_cutoff=cutoff)
        if distance < best_distance:
            best_distance = distance
            best_territory = territory
    if best_territory is None:
        return None
    log.debug(
        "Guessing country: %r -> %s (distance %d)",
        name,
        best_territory.code,
        best_distance,
    )
    return best_territory


@lru_cache(maxsize=MEMO_MEDIUM)
def lookup_territory(text: str, fuzzy: bool = False) -> Optional[Territory]:
    """Lookup a territory by various codes and names.

    Args:
        text: The text to lookup, which can be a code, name, or other identifier.
        fuzzy: If true, try a fuzzy search if the direct lookup didn't succeed.

    Returns:
        An instance of Territory if found, otherwise None.
    """
    territory = lookup_by_identifier(text)
    if territory is not None:
        return territory
    normalized_name = normalize_territory_name(text)
    with resource_lock:
        names = _get_territory_names()
    if normalized_name in names:
        return names[normalized_name]
    if fuzzy:
        return _fuzzy_search(normalized_name)
    log.debug("No territory found for %r", text)
    return None
