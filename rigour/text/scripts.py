import unicodedata
from functools import lru_cache
from typing import Tuple

from rigour.text.script_data import BLOCK_TAGS, ALPHABET, HISTORIC, FUNKY, LATIN


@lru_cache(maxsize=5000)
def char_tags(char: str) -> Tuple[int, ...]:
    """Get the tags applicable to a particular character."""
    codepoint = ord(char)
    for start, end, tags in BLOCK_TAGS:
        if start <= codepoint <= end:
            return tags
    return ()


@lru_cache(maxsize=5000)
def is_alpha(char: str) -> bool:
    """Check if a character is alphabetic. This improves on the function implemented on
    `str` by including characters for the whole unicode range."""
    category = unicodedata.category(char)[0]
    return category == "L"


@lru_cache(maxsize=5000)
def is_alphanum(char: str) -> bool:
    """Check if a character is alpha-numeric."""
    category = unicodedata.category(char)[0]
    return category in ("L", "N")


def is_modern_alphabet(word: str) -> bool:
    """Check if a word is written in a modern alphabet. The term alphabet is
    used in a narrow sense here: it includes only alphabets that have vowels and
    are safely transliterated to latin. Basically: Cyrillic, Greek, Armenian,
    and Latin."""
    for char in word:
        tags = char_tags(char)
        if not len(tags):
            continue
        if ALPHABET not in tags:
            return False
        if HISTORIC in tags or FUNKY in tags:
            return False
    return True


def is_latin(word: str) -> bool:
    """Check if a word is written in the latin alphabet."""
    for char in word:
        tags = char_tags(char)
        if not len(tags):
            continue
        if LATIN not in tags:
            return False
        # CHECK: I don't think this exists in practice:
        # if HISTORIC in tags or FUNKY in tags:
        #     return False
    return True
