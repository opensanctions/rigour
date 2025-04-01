import re
import logging
import unicodedata
from functools import cache
from typing import Callable, Dict, List, Optional
from normality.constants import WS
from normality.transliteration import ascii_text
from normality.util import Categories

from rigour.data.addresses.data import NORMALISATIONS

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

log = logging.getLogger(__name__)


def _normalize_address_text(address: str, latinize: bool = False, sep: str = WS) -> str:
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
        parts.append(token_str)
    return sep.join(parts)


@cache
def _common_replacer(latinize: bool = False) -> Callable[[str], str]:
    """Create a function that replaces common address tokens with their normalized forms.

    Args:
        sep: The separator to use for joining the normalized tokens.
        latinize: Whether to convert non-Latin characters to their Latin equivalents.

    Returns:
        A function that takes a string and returns its normalized form.
    """
    mapping: Dict[str, str] = {}
    for repl, values in NORMALISATIONS.items():
        repl_norm = _normalize_address_text(repl, latinize=latinize, sep=WS)
        for value in values:
            value_norm = _normalize_address_text(value, latinize=latinize, sep=WS)
            if value_norm != repl_norm:
                if value_norm in mapping:
                    log.warning("Duplicate mapping for %s", value_norm)
                mapping[value_norm] = repl_norm

    mappings = "|".join(mapping.keys())
    regex = re.compile(f"\\b({mappings})\\b", re.UNICODE)

    def _replace_match(match: re.Match[str]) -> str:
        matched_text = match.group(1)
        return mapping.get(matched_text, matched_text)

    def _replacer(text: str) -> str:
        return regex.sub(_replace_match, text)

    return _replacer


def normalize_address(
    address: str, latinize: bool = False, min_length: int = 4, sep: str = WS
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
    norm_address = _normalize_address_text(address, latinize=latinize, sep=WS)
    norm_address = _common_replacer(latinize)(norm_address)
    if sep != WS:
        norm_address = norm_address.replace(WS, sep)
    if len(norm_address) < min_length:
        return None
    return norm_address
