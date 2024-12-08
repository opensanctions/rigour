from typing import Dict, List, Tuple
from itertools import permutations, product, zip_longest

from rigour.text.distance import levenshtein


def align_name_parts(left: List[str], right: List[str]) -> List[Tuple[str, str]]:
    """Align two names for comparison by sorting in the levenshtein-cheapest manner.

    Args:
        left: A list of strings.
        right: A list of strings.
        func: A function to compute the distance between two strings (bigger value is more dislike).

    Returns:
        A list of tuples with the aligned strings.
    """
    distances: Dict[Tuple[str, str], int] = {}
    for le, ri in product(left, right):
        if le == ri:
            distances[(le, ri)] = 0
        elif (le, ri) not in distances:
            distances[(le, ri)] = levenshtein(le, ri)
        distances[(ri, le)] = distances[(le, ri)]

    long, short = (left, right) if len(left) > len(right) else (right, left)
    result: List[Tuple[str, str]] = []
    min_distance = 2**64
    for long_ordering in permutations(long):
        ord_distance = 0
        for a, b in zip_longest(short, long_ordering, fillvalue=""):
            ord_distance += distances.get((a, b), max(len(a), len(b)))
        if ord_distance < min_distance:
            min_distance = ord_distance
            result = [
                (a, b) for a, b in zip_longest(short, long_ordering, fillvalue="")
            ]
    if right == short:
        result = [(b, a) for a, b in result]
    return result
