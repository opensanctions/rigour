from typing import Iterable, Set
from rigour.territories.territory import Territory, get_index


def territories_intersect(left: Iterable[str], right: Iterable[str]) -> Set[str]:
    """Get the intersection of two territory code lists. This takes into account
    parent-child relationships and contested claims regarding territories.

    Args:
        left: A list of territory codes.
        right: A list of territory codes.

    Returns:
        A set of territory codes that are common to both lists, considering
        hierarchical and claim relationships. The most narrow codes are returned.
    """
    index = get_index()
    left_set: Set[Territory] = set(index[code] for code in left if code in index)
    right_set: Set[Territory] = set(index[code] for code in right if code in index)
    common: Set[Territory] = set()
    for cand in left_set:
        if cand in right_set:
            common.add(cand)
            continue
        if cand.parent is not None and cand.parent in right_set:
            common.add(cand)
            continue
        for claim in cand.claims:
            if claim in right_set:
                common.add(cand)
    for cand in right_set:
        if cand.parent is not None and cand.parent in left_set:
            common.add(cand)
            continue
        for claim in cand.claims:
            if claim in left_set:
                common.add(cand)
    return {t.code for t in common}
