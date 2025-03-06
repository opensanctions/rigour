from functools import cache
from typing import Dict, Optional
from rigour.data.territories.data import TERRITORIES
from rigour.territories.territory import Territory


@cache
def _get_index() -> Dict[str, Territory]:
    index: Dict[str, Territory] = {}
    for code, data in TERRITORIES.items():
        index[code] = Territory(index, code, data)
    for territory in index.values():
        territory._validate()
    return index


def get_territory(code: str) -> Optional[Territory]:
    """Get a territory object for the given code.

    Args:
        code: Country, territory or jurisdiction code.

    Returns:
        A territory object.
    """
    index = _get_index()
    return index.get(code)


def get_territory_by_qid(qid: str) -> Optional[Territory]:
    """Get a territory object for the given Wikidata QID.

    Args:
        qid: Wikidata QID.

    Returns:
        A territory object.
    """
    for territory in _get_index().values():
        if territory.qid == qid:
            return territory
        if qid in territory.other_qids:
            return territory
    return None
