import unicodedata
from typing import List
from normality.constants import WS
from normality.cleaning import category_replace, collapse_spaces
from normality.util import Categories
from fingerprints.cleanup import CHARACTERS_REMOVE_RE

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


def prepare_tokenize_name(text: str) -> str:
    """Prepare a name for tokenization."""
    text = text.lower()
    text = CHARACTERS_REMOVE_RE.sub("", text)
    text = category_replace(text, replacements=TOKEN_SEP_CATEGORIES) or ""
    text = collapse_spaces(text) or ""
    return text


def tokenize_name(text: str, min_length: int = 1) -> List[str]:
    """Split a person or entity's name into name parts."""
    # FIXME: Do we want to support CJK scripts at some stage?
    tokens: List[str] = []
    token: List[str] = []
    for char in text:
        if char in ".'’":
            continue
        # TODO: do we want to special case Arabic name parts like
        # al-, el-, il- ?
        cat = unicodedata.category(char)
        chr = TOKEN_SEP_CATEGORIES.get(cat, char)
        if chr is None:
            continue
        if chr == WS:
            # TODO: do we want to support throwing away name prefixes
            # (like Mr., Sir, etc.) here?
            if len(token) >= min_length:
                tokens.append("".join(token))
            token.clear()
            continue
        token.append(chr)

    if len(token) >= min_length:
        tokens.append("".join(token))
    return tokens
