import unicodedata
from functools import lru_cache
from typing import Tuple, Optional

from rigour.text.script_data import BLOCK_TAGS, ALPHABET, HISTORIC, FUNKY, LATIN
from rigour.util import MEMO_MEDIUM


@lru_cache(maxsize=MEMO_MEDIUM)
def char_tags(char: str) -> Tuple[int, ...]:
    """Get the tags applicable to a particular character."""
    codepoint = ord(char)
    for start, end, tags in BLOCK_TAGS:
        if start <= codepoint <= end:
            return tags
    return ()


@lru_cache(maxsize=MEMO_MEDIUM)
def is_alpha(char: str) -> bool:
    """Check if a character is alphabetic. This improves on the function implemented on
    `str` by including characters for the whole unicode range."""
    category = unicodedata.category(char)[0]
    return category == "L"


@lru_cache(maxsize=MEMO_MEDIUM)
def is_alphanum(char: str) -> bool:
    """Check if a character is alpha-numeric."""
    category = unicodedata.category(char)[0]
    return category in ("L", "N")


@lru_cache(maxsize=MEMO_MEDIUM)
def is_modern_alphabet_char(char: str) -> Optional[bool]:
    tags = char_tags(char)
    if not len(tags):
        return None
    if ALPHABET not in tags:
        return False
    if HISTORIC in tags or FUNKY in tags:
        return False
    return True


def is_modern_alphabet(word: str) -> bool:
    """Check if a word is written in a modern alphabet. The term alphabet is
    used in a narrow sense here: it includes only alphabets that have vowels and
    are safely transliterated to latin. Basically: Cyrillic, Greek, Armenian,
    and Latin."""
    for char in word:
        is_char = is_modern_alphabet_char(char)
        if is_char is False:
            return False
    return True


@lru_cache(maxsize=MEMO_MEDIUM)
def is_latin_char(char: str) -> Optional[bool]:
    tags = char_tags(char)
    if not len(tags):
        return None
    if LATIN not in tags:
        return False
    return True


def is_latin(word: str) -> bool:
    """Check if a word is written in the latin alphabet."""
    for char in word:
        is_char = is_latin_char(char)
        if is_char is False:
            return False
    return True
