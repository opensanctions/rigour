import unicodedata
from typing import List
from normality.constants import WS
from normality.util import Categories

# PREFIXES = ["el", "al", "il"]
TOKEN_SEP_CATEGORIES: Categories = {
    "Cc": WS,
    "Cf": None,
    # "Cs": None,
    "Co": None,
    "Cn": None,
    "Lm": None,
    "Mn": None,
    "Mc": WS,
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


def tokenize_name(text: str, token_min_length: int = 1) -> List[str]:
    """Split a person or entity's name into name parts."""
    # FIXME: Do we want to support CJK scripts at some stage?
    tokens: List[str] = []
    token: List[str] = []
    # TODO: Do we want to do some form of unicode normalization here?
    # text = unicodedata.normalize("NFC", text)
    for char in text:
        if char in ".'’":
            continue
        cat = unicodedata.category(char)
        chr = TOKEN_SEP_CATEGORIES.get(cat, char)
        if chr is None:
            continue
        if chr == WS:
            if len(token) >= token_min_length:
                tokens.append("".join(token))
            token.clear()
            continue
        token.append(chr)

    if len(token) >= token_min_length:
        tokens.append("".join(token))
    return tokens
