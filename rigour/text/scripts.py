from functools import lru_cache
from typing import Optional

from rigour.data.text.scripts import RANGES, LATIN_CHARS, LATINIZABLE_CHARS
from rigour.util import MEMO_MEDIUM

# There are no non-Latin characters below this codepoint:
LATIN_BLOCK = 740
# Hangul is surprisingly good in terms of transliteration, so we allow it:
LATINIZE_SCRIPTS = {"Hangul", "Cyrillic", "Greek", "Armenian", "Latin", "Georgian"}


def get_script(codepoint: int) -> Optional[str]:
    """Get the script of a character."""
    for (start, end), script in RANGES.items():
        if start <= codepoint <= end:
            return script
    return None


@lru_cache(maxsize=MEMO_MEDIUM)
def can_latinize_cp(cp: int) -> Optional[bool]:
    """Check if a codepoint should be latinized."""
    char = chr(cp)
    if not char.isalnum():
        return None
    script = get_script(cp)
    if script is None:
        return None
    if script in LATINIZE_SCRIPTS:
        return True
    return False


def can_latinize(word: str) -> bool:
    """Check if a word should be latinized using automated transliteration. This limits
    the scope of transliteration to specific scripts which are well-suited for automated
    romanisation.

    Args:
        word (str): The word to check.

    Returns:
        bool: True if the word should be latinized, False otherwise.
    """
    for char in word:
        cp = ord(char)
        if cp in LATINIZABLE_CHARS:
            continue
        if cp < LATIN_BLOCK:
            continue
        if can_latinize_cp(cp) is False:
            return False
    return True


def is_modern_alphabet(word: str) -> bool:
    """Check if a word is written in a modern alphabet. The term alphabet is
    used in a narrow sense here: it includes only alphabets that have vowels and
    are safely transliterated to latin. Basically: Cyrillic, Greek, Armenian,
    and Latin."""
    for char in word:
        cp = ord(char)
        if cp in LATINIZABLE_CHARS:
            continue
        if cp < LATIN_BLOCK:
            continue
        if not char.isalnum():
            continue
        return False
    return True


def is_latin(word: str) -> bool:
    """Check if a word is written in the latin alphabet."""
    for char in word:
        cp = ord(char)
        if cp in LATIN_CHARS:
            continue
        if cp < LATIN_BLOCK:
            continue
        if char.isalnum():
            return False
    return True
