from typing import Optional
from functools import lru_cache
from jellyfish import damerau_levenshtein_distance, levenshtein_distance
from jellyfish import jaro_winkler_similarity

CACHE = 1024
MAX_TEXT = 128


@lru_cache(maxsize=CACHE)
def dam_levenshtein(left: str, right: str) -> int:
    """Compute the Damerau-Levenshtein distance between two strings.

    Args:
        left: A string.
        right: A string.

    Returns:
        An integer of changed characters.
    """
    if left == right:
        return 0
    return damerau_levenshtein_distance(left[:MAX_TEXT], right[:MAX_TEXT])


@lru_cache(maxsize=CACHE)
def levenshtein(left: str, right: str) -> int:
    """Compute the Levenshtein distance between two strings.

    Args:
        left: A string.
        right: A string.

    Returns:
        An integer of changed characters.
    """
    if left == right:
        return 0
    return levenshtein_distance(left[:MAX_TEXT], right[:MAX_TEXT])


def levenshtein_similarity(
    left: str,
    right: str,
    max_edits: Optional[int] = None,
    max_percent: float = 0.5,
) -> float:
    """Compute the levenshtein similarity of two strings. The similiarity is
    the percentage distance measured against the length of the longest string.

    Args:
        left: A string.
        right: A string.
        max_edits: The maximum number of edits allowed.
        max_percent: The maximum percentage of edits allowed.

    Returns:
        A float between 0.0 and 1.0.
    """
    distance = dam_levenshtein(left, right)
    left_len = len(left)
    right_len = len(right)
    if left_len == 0 or right_len == 0:
        return 0.0
    # Skip results with an overall distance of more than N characters:
    pct_edits = min(left_len, right_len) * max_percent
    max_edits_ = min(max_edits, pct_edits) if max_edits is not None else pct_edits
    if distance > max_edits_:
        return 0.0
    return 1.0 - (float(distance) / max(left_len, right_len))


@lru_cache(maxsize=CACHE)
def jaro_winkler(left: str, right: str) -> float:
    """Compute the Jaro-Winkler similarity of two strings.

    Args:
        left: A string.
        right: A string.

    Returns:
        A float between 0.0 and 1.0.
    """
    score = jaro_winkler_similarity(left[:MAX_TEXT], right[:MAX_TEXT])
    return score if score > 0.6 else 0.0
