import math
from typing import Optional
from functools import lru_cache
from rapidfuzz.distance import Levenshtein, DamerauLevenshtein, JaroWinkler

from rigour import env
from rigour.util import MEMO_SMALL


@lru_cache(maxsize=MEMO_SMALL)
def dam_levenshtein(
    left: str,
    right: str,
    max_length: int = env.MAX_NAME_LENGTH,
    max_edits: Optional[int] = None,
) -> int:
    """Compute the Damerau-Levenshtein distance between two strings.

    Args:
        left: A string.
        right: A string.

    Returns:
        An integer of changed characters.
    """
    if left == right:
        return 0
    return DamerauLevenshtein.distance(
        left[:max_length],
        right[:max_length],
        score_cutoff=max_edits,
    )


@lru_cache(maxsize=MEMO_SMALL)
def levenshtein(
    left: str,
    right: str,
    max_length: int = env.MAX_NAME_LENGTH,
    max_edits: Optional[int] = None,
) -> int:
    """Compute the Levenshtein distance between two strings.

    Args:
        left: A string.
        right: A string.

    Returns:
        An integer of changed characters.
    """
    if left == right:
        return 0
    return Levenshtein.distance(
        left[:max_length],
        right[:max_length],
        score_cutoff=max_edits,
    )


def levenshtein_similarity(
    left: str,
    right: str,
    max_edits: Optional[int] = env.LEVENSHTEIN_MAX_EDITS,
    max_percent: float = env.LEVENSHTEIN_MAX_PERCENT,
    max_length: int = env.MAX_NAME_LENGTH,
) -> float:
    """Compute the Damerau Levenshtein similarity of two strings. The similiarity is
    the percentage distance measured against the length of the longest string.

    Args:
        left: A string.
        right: A string.
        max_edits: The maximum number of edits allowed.
        max_percent: The maximum fraction of the shortest string that is allowed to be edited.

    Returns:
        A float between 0.0 and 1.0.
    """
    left_len = len(left)
    right_len = len(right)
    if left_len == 0 or right_len == 0:
        return 0.0

    # Skip results with an overall distance of more than N characters:
    pct_edits = math.ceil(min(left_len, right_len) * max_percent)
    max_edits_ = min(max_edits, pct_edits) if max_edits is not None else pct_edits
    if abs(left_len - right_len) > max_edits_:
        return 0.0

    distance = levenshtein(left, right, max_length=max_length, max_edits=max_edits_)
    if distance > max_edits_:
        return 0.0
    return 1.0 - (float(distance) / max(left_len, right_len))


def is_levenshtein_plausible(
    left: str,
    right: str,
    max_edits: Optional[int] = env.LEVENSHTEIN_MAX_EDITS,
    max_percent: float = env.LEVENSHTEIN_MAX_PERCENT,
    max_length: int = env.MAX_NAME_LENGTH,
) -> bool:
    """A sanity check to post-filter name matching results based on a budget
    of allowed Levenshtein distance. This basically cuts off results where
    the Jaro-Winkler or Metaphone comparison was too lenient.

    Args:
        left: A string.
        right: A string.
        max_edits: The maximum number of edits allowed.
        max_percent: The maximum percentage of edits allowed.

    Returns:
        A boolean.
    """
    left = left[:max_length]
    right = right[:max_length]
    pct_edits = math.ceil(min(len(left), len(right)) * max_percent)
    max_edits_ = min(max_edits, pct_edits) if max_edits is not None else pct_edits
    distance = levenshtein(left, right, max_length, max_edits=max_edits_)
    return distance <= max_edits_


@lru_cache(maxsize=MEMO_SMALL)
def jaro_winkler(left: str, right: str, max_length: int = env.MAX_NAME_LENGTH) -> float:
    """Compute the Jaro-Winkler similarity of two strings.

    Args:
        left: A string.
        right: A string.

    Returns:
        A float between 0.0 and 1.0.
    """
    score = JaroWinkler.normalized_similarity(left[:max_length], right[:max_length])
    return score if score > 0.6 else 0.0
