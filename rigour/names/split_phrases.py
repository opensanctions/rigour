import re
from functools import cache

from rigour._core import name_split_phrases_list


@cache
def _split_phrase_regex() -> re.Pattern[str]:
    """Compile the split-phrase regex from the Rust-owned wordlist."""
    patterns = [re.escape(phrase) for phrase in name_split_phrases_list()]
    pattern = rf"(\b({'|'.join(patterns)})\b)"
    return re.compile(pattern, re.I | re.U)


def contains_split_phrase(string: str) -> bool:
    """Check if the string contains name split phrases e.g. a.k.a."""
    return _split_phrase_regex().search(string) is not None
