from normality.constants import WS
from normality.cleaning import category_replace, collapse_spaces
from normality.util import Categories
from fingerprints.cleanup import CHARACTERS_REMOVE_RE

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
    text = category_replace(text, replacements=TOKEN_SEP_CATEGORIES) or ''
    text = collapse_spaces(text) or ""
    return text
