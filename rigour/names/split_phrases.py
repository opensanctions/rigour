import re
from typing import Tuple
from functools import cache

from rigour.data.names.data import NAME_SPLIT_PHRASES


@cache
def re_split_phrases(phrases: Tuple[str, ...]) -> re.Pattern[str]:
    """Compile a regex pattern to match common name split phrases."""
    patterns = [re.escape(phrase) for phrase in phrases]
    pattern = rf"(\b({'|'.join(patterns)})\b)"
    return re.compile(pattern, re.I | re.U)


def contains_split_phrase(string: str) -> bool:
    """Check if the string contains name split phrases e.g. a.k.a."""
    return re_split_phrases(NAME_SPLIT_PHRASES).search(string) is not None
