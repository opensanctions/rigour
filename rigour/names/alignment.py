from itertools import product
from typing import List, Optional, Tuple

from rigour.names.part import NamePart
from rigour.names.tag import NamePartTag
from rigour.text.distance import dam_levenshtein


def _name_levenshtein(query: List[NamePart], result: List[NamePart]) -> float:
    query_str = "".join([p.comparable for p in query])
    result_str = "".join([p.comparable for p in result])
    max_len = max(len(query_str), len(result_str))
    if query_str == result_str or max_len == 0:
        return 1.0
    distance = dam_levenshtein(query_str, result_str)
    score = 1 - (distance / max_len)
    if score < 0.3:
        return 0.0
    return score


def _pack_short_parts(
    part: NamePart, other: NamePart, options: List[NamePart]
) -> List[NamePart]:
    packed: List[NamePart] = [other]
    for op in options:
        if op in packed:
            continue
        if not NamePartTag.can_match(part.tag, op.tag):
            continue
        base_str = "".join([p.comparable for p in packed])
        if len(base_str) >= len(part.form):
            break
        best_score = _name_levenshtein([part], packed)
        best_packed = None
        for i in range(len(packed) + 1):
            next_packed = packed.copy()
            next_packed.insert(i, op)
            next_score = _name_levenshtein([part], next_packed)
            if next_score > best_score:
                best_score = next_score
                best_packed = next_packed
        if best_packed is not None:
            packed = best_packed
    return packed


def align_person_name_order(
    left: List[NamePart], right: List[NamePart]
) -> Tuple[List[NamePart], List[NamePart]]:
    """Aligns the name parts of a person name for two names based on their tags and their string
    similarity such that the most similar name parts are matched.

    Args:
        left (List[NamePart]): The name parts of the first name.
        right (List[NamePart]): The name parts of the second name.

    Returns:
        Tuple[List[NamePart], List[NamePart]]: A tuple containing the sorted name parts of both names.
    """
    if not len(left):
        return (left, NamePart.tag_sort(right))

    left_sorted: List[NamePart] = []
    right_sorted: List[NamePart] = []

    left_unused = sorted(left, key=len, reverse=True)
    right_unused = sorted(right, key=len, reverse=True)
    while len(left_unused) > 0 and len(right_unused) > 0:
        best_score = 0.0
        best_left_parts: Optional[List[NamePart]] = None
        best_right_parts: Optional[List[NamePart]] = None
        for qp, rp in product(left_unused, right_unused):
            if not NamePartTag.can_match(qp.tag, rp.tag):
                continue
            if qp.comparable == rp.comparable:
                best_score = 1.0
                best_left_parts = [qp]
                best_right_parts = [rp]
                break
            # check the Levenshtein distance between the two parts
            score = _name_levenshtein([qp], [rp])
            if score > best_score:
                best_left_parts = [qp]
                best_right_parts = [rp]
                if len(qp.form) > len(rp.form):
                    best_right_parts = _pack_short_parts(qp, rp, right_unused)
                elif len(rp.form) > len(qp.form):
                    best_left_parts = _pack_short_parts(rp, qp, left_unused)
                best_score = _name_levenshtein(best_left_parts, best_right_parts)

        if best_score == 0.0:
            # no match found, break out of the loop
            break

        if best_left_parts is not None:
            left_sorted.extend(best_left_parts)
            for qp in best_left_parts:
                left_unused.remove(qp)
        if best_right_parts is not None:
            right_sorted.extend(best_right_parts)
            for rp in best_right_parts:
                right_unused.remove(rp)

    if not len(left_sorted):
        return (NamePart.tag_sort(left), NamePart.tag_sort(right))

    left_sorted.extend(left_unused)
    right_sorted.extend(right_unused)
    return (left_sorted, right_sorted)
