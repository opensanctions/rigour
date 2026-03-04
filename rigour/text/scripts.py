from functools import lru_cache
from typing import Optional

from rigour.data.text.scripts import RANGES, LATIN_CHARS, LATINIZABLE_CHARS
from rigour.util import MEMO_MEDIUM

# There are no non-Latin characters below this codepoint:
LATIN_BLOCK = 740
# Hangul is surprisingly good in terms of transliteration, so we allow it:
LATINIZE_SCRIPTS = {"Hangul", "Cyrillic", "Greek", "Armenian", "Latin", "Georgian"}
# Scripts that are denser than Latin (fewer code points per unit of meaning/sound)
# Includes Hangul along with logographic scripts because it is also denser by virtue
# of encoding syllables rather than individual sounds.
# https://en.wikipedia.org/wiki/List_of_writing_systems#Logographic_systems
DENSE_SCRIPTS = {"Han", "Hiragana", "Katakana", "Hangul"}


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


def is_dense_script(word: str) -> bool:
    """Check if a word contains characters from a script that is notably denser
    than Latin: one that encodes more meaning/sound per unicode code point
    
    This can be a rough proxy for languages scripts which don't use spaces to
    separate names, although it includes Hangul which uses spaces to separate other
    words.

    Args:
        word (str): The word to check.

    Returns:
        bool: True if the word contains any character from a dense script.
    """
    for char in word:
        if not char.isalnum():
            continue
        script = get_script(ord(char))
        if script in DENSE_SCRIPTS:
            return True
    return False
