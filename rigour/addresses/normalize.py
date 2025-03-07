import unicodedata
from typing import List, Optional
from normality.constants import WS
from normality.transliteration import ascii_text
from normality.util import Categories

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

COMMON = {
    "street": "st",
    "road": "rd",
    "number": "no",
    "avenue": "ave",
    "room": "rm",
    "building": "bldg",
    "boulevard": "blvd",
    "strasse": "str",
    "strase": "str",
    "ulitsa": "ul",
    "drive": "dr",
    "platz": "pl",
    "square": "sq",
    "plaza": "plz",
    "piazza": "pza",
    "place": "pl",
    "center": "ctr",
    "centre": "ctr",
    "park": "pk",
    "garden": "gd",
    "gardens": "gd",
    "republic": "rep",
    "republik": "rep",
    "republique": "rep",
    "repubblica": "rep",
    "west": "w",
    "east": "e",
    "north": "n",
    "south": "s",
    "apartment": "apt",
    "apartments": "apt",
    "apts": "apt",
    "suite": "ste",
    "floor": "fl",
    "department": "dept",
}


def normalize_address(
    address: str, latinize: bool = False, min_length: int = 4
) -> Optional[str]:
    """Normalize the given address string for comparison, in a way that is destructive to
    the ability for displaying it (makes it ugly).

    Args:
        address: The address to be normalized.
        latinize: Whether to convert non-Latin characters to their Latin equivalents.
        min_length: Minimum length of the normalized address.

    Returns:
        The normalized address.
    """
    tokens: List[List[str]] = []
    token: List[str] = []
    for char in address.lower():
        cat = unicodedata.category(char)
        chr = TOKEN_SEP_CATEGORIES.get(cat, char)
        if chr is None:
            continue
        if chr == WS:
            if len(token):
                tokens.append(token)
            token = []
            continue
        token.append(chr)
    if len(token):
        tokens.append(token)

    parts: List[str] = []
    for token in tokens:
        token_str: Optional[str] = "".join(token)
        if latinize:
            token_str = ascii_text(token_str)
        if token_str is None:
            continue
        token_str = COMMON.get(token_str, token_str)
        parts.append(token_str)
    norm_address = "".join(parts)
    if len(norm_address) < min_length:
        return None
    return norm_address
