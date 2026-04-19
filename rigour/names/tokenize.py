import unicodedata
from functools import lru_cache
from typing import List, Optional
from normality.constants import WS
from normality.util import Categories

from rigour.util import MEMO_TINY, MEMO_MEDIUM

# PREFIXES = ["el", "al", "il"]
SKIP_CHARACTERS = (
    "."  # U+002E FULL STOP (abbreviations: U.S.A.)
    "\u0027"  # U+0027 APOSTROPHE (ASCII: don't)
    "\u2018"  # U+2018 LEFT SINGLE QUOTATION MARK
    "\u2019"  # U+2019 RIGHT SINGLE QUOTATION MARK (curly apostrophe)
    "\u02bc"  # U+02BC MODIFIER LETTER APOSTROPHE
    "\u02b9"  # U+02B9 MODIFIER LETTER PRIME
    "\u0060"  # U+0060 GRAVE ACCENT
    "\u00b4"  # U+00B4 ACUTE ACCENT
)

# Lm (Letter, modifier) characters that carry meaning in names and should be
# kept as part of tokens rather than deleted. Most Lm characters are phonetic
# notation (superscript markers like ʰ, ʲ) which are noise in name data, but
# these specific ones appear in real CJK names.
KEEP_CHARACTERS = (
    "\u30fc"  # U+30FC KATAKANA-HIRAGANA PROLONGED SOUND MARK (ー)
    "\uff70"  # U+FF70 HALFWIDTH KATAKANA-HIRAGANA PROLONGED SOUND MARK (ｰ)
    "\u3005"  # U+3005 IDEOGRAPHIC ITERATION MARK (々)
)

TOKEN_SEP_CATEGORIES: Categories = {
    "Cc": WS,
    "Cf": None,
    # "Cs": None,
    "Co": None,
    "Cn": None,
    "Lm": None,
    "Mn": None,
    # Mc (spacing combining marks) are kept — they are vowel signs in Brahmic/Indic
    # scripts (Myanmar, Devanagari, Tamil, Thai, etc.) and essential parts of syllables.
    # No Mc characters exist in Latin, Cyrillic, Greek, CJK, or Arabic ranges.
    # "Mc": WS,
    "Me": None,
    "No": None,
    "Zs": WS,
    "Zl": WS,
    "Zp": WS,
    "Pc": WS,
    "Pd": WS,
    "Ps": WS,
    "Pe": WS,
    "Pi": WS,
    "Pf": WS,
    "Po": WS,
    "Sm": WS,
    "Sc": None,
    "Sk": None,
    "So": WS,
}


class _TokenizerLookup(dict[int, Optional[int]]):
    """Lazy str.translate() table for tokenize_name().

    Caches codepoint → replacement on first encounter, up to a limit of entries.
    SKIP_CHARACTERS are pre-seeded as None (deleted, not treated as separators).
    """

    def __missing__(self, codepoint: int) -> Optional[int]:
        char = chr(codepoint)
        if char in KEEP_CHARACTERS:
            val: Optional[int] = codepoint  # keep as-is
            if len(self) < MEMO_MEDIUM:
                self[codepoint] = val
            return val
        cat = unicodedata.category(char)
        replacement = TOKEN_SEP_CATEGORIES.get(cat)
        if replacement is None and cat not in TOKEN_SEP_CATEGORIES:
            val = codepoint  # keep as-is
        elif not replacement:
            val = None  # delete
        else:
            val = ord(replacement[0])  # e.g. WS → space
        if len(self) < MEMO_MEDIUM:
            self[codepoint] = val
        return val


_TOKENIZER = _TokenizerLookup({ord(c): None for c in SKIP_CHARACTERS})


def tokenize_name(text: str, token_min_length: int = 1) -> List[str]:
    """Split a person or entity’s name into name parts."""
    text = text.translate(_TOKENIZER)
    return [t for t in text.split() if len(t) >= token_min_length]


@lru_cache(maxsize=MEMO_TINY)
def normalize_name(name: Optional[str], sep: str = WS) -> Optional[str]:
    """Normalize a name for tokenization and matching."""
    if name is None:
        return None
    joined = sep.join(tokenize_name(name.casefold()))
    if len(joined) == 0:
        return None
    return joined
