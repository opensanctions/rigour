import string
import logging
import unicodedata
from functools import cache
from typing import Dict, List, Optional
from normality.constants import WS
from normality.transliteration import ascii_text
from normality.util import Categories

from rigour.text.dictionary import Replacer

CHARS_ALLOWED = "&№" + string.ascii_letters + string.digits
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
        if char in CHARS_ALLOWED:
            chr: Optional[str] = char
        else:
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
    norm_address = WS.join(parts)
    if len(norm_address) < min_length:
        return None
    return norm_address


@cache
def _address_replacer(latinize: bool = False) -> Replacer:
    """Create a function that replaces common address tokens with their normalized forms.

    Args:
        sep: The separator to use for joining the normalized tokens.
        latinize: Whether to convert non-Latin characters to their Latin equivalents.

    Returns:
        A function that takes a string and returns its normalized form.
    """
    from rigour.data.addresses.data import FORMS

    mapping: Dict[str, str] = {}
    for repl, values in FORMS.items():
        repl_norm = normalize_address(repl, latinize=latinize, min_length=1)
        if repl_norm is None:
            log.warning("Replacement is normalized to null: %r", repl)
            continue
        mapping[repl_norm] = repl_norm
        for value in values:
            value_norm = normalize_address(value, latinize=latinize, min_length=1)
            if value_norm is None:
                log.warning("Value is normalized to null [%r]: %r", repl, value)
                continue
            if value_norm != repl_norm:
                if value_norm in mapping and mapping[value_norm] != repl_norm:
                    log.warning(
                        "Duplicate mapping for %s (%s and %s)",
                        value_norm,
                        repl_norm,
                        mapping[value_norm],
                    )  # pragma: no cover
                mapping[value_norm] = repl_norm
    return Replacer(mapping, ignore_case=True)


def remove_address_keywords(
    address: str, latinize: bool = False, replacement: str = WS
) -> Optional[str]:
    """Remove common address keywords (such as "street", "road", "south", etc.) from the
    given address string. The address string is assumed to have already been normalized
    using `normalize_address`.

    The output may contain multiple consecutive whitespace characters, which are not collapsed.

    Args:
        address: The address to be cleaned.
        latinize: Whether to convert non-Latin characters to their Latin equivalents.

    Returns:
        The address, without any stopwords.
    """
    replacer = _address_replacer(latinize=latinize)
    return replacer.remove(address, replacement=replacement)


def shorten_address_keywords(address: str, latinize: bool = False) -> Optional[str]:
    """Shorten common address keywords (such as "street", "road", "south", etc.) in the
    given address string. The address string is assumed to have already been normalized
    using `normalize_address`.

    Args:
        address: The address to be cleaned.
        latinize: Whether to convert non-Latin characters to their Latin equivalents.

    Returns:
        The address, with keywords shortened.
    """
    replacer = _address_replacer(latinize=latinize)
    return replacer(address)
