import re
import string
import logging
import unicodedata
from functools import cache
from typing import Dict, List, Optional, Tuple
from normality import ascii_text
from normality.constants import WS
from normality.util import Categories

from rigour.territories.lookup import _load_territory_names
from rigour.util import resource_lock, unload_module

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
    """Build a comparison key from an address.

    Casefolds, replaces punctuation/symbols with whitespace,
    tokenises on Unicode general-category, and rejoins with
    single-space separators. The output is a flat lowercase token
    sequence suitable for substring matching, equality keys, or
    feeding :func:`shorten_address_keywords` /
    :func:`remove_address_keywords` — **not** a display form.

    Args:
        address: The address to normalise.
        latinize: When `True`, transliterate non-ASCII tokens to
            ASCII via `normality.ascii_text`. Default `False`
            preserves the original script.
        min_length: Reject the result as `None` if it would be
            shorter than this many characters. Defaults to 4 to
            filter out single-token noise.

    Returns:
        Normalised address, or `None` when the result is shorter
        than `min_length`.
    """
    tokens: List[List[str]] = []
    token: List[str] = []
    for char in address.casefold():
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
        token_str = "".join(token)
        if latinize:
            token_str = ascii_text(token_str)
        if len(token_str) == 0:
            continue
        parts.append(token_str)
    norm_address = WS.join(parts)
    if len(norm_address) < min_length:
        return None
    return norm_address


@cache
def _address_replacer(latinize: bool = False) -> Tuple[re.Pattern[str], Dict[str, str]]:
    """Build the (compiled regex, form → target mapping) tuple used by
    `shorten_address_keywords` and `remove_address_keywords`.

    Both halves are built once per `latinize` flag and cached for the
    lifetime of the process. The regex is shaped
    `(?<!\\w)(form|...)(?!\\w)` with longest-form-first ordering so the
    multi-token forms (e.g. `"united arab emirates"` → `"ae"`) win over
    their single-token components.
    """
    from rigour.data.addresses.data import FORMS
    from rigour._core import ordinals_dict

    ordinals = [(str(k), v) for k, v in ordinals_dict().items()]
    forms = list(FORMS.items()) + ordinals

    mapping: Dict[str, str] = {}
    for repl, values in forms:
        repl_norm = normalize_address(repl, latinize=latinize, min_length=1)
        if repl_norm is None:  # pragma: no cover
            log.warning("Replacement is normalized to null: %r", repl)
            continue
        mapping[repl_norm] = repl_norm
        for value in values:
            value_norm = normalize_address(value, latinize=latinize, min_length=1)
            if value_norm is None:
                # log.warning("Value is normalized to null [%r]: %r", repl, value)
                continue
            if value_norm != repl_norm:
                if value_norm in mapping and mapping[value_norm] != repl_norm:
                    log.warning(
                        "Duplicate mapping for %s (%s and %s)",
                        value,
                        repl_norm,
                        mapping[value_norm],
                    )  # pragma: no cover
                mapping[value_norm] = repl_norm

    # ignore weak names for now, as they cause too many false positives
    for territory, names, _ in _load_territory_names():
        for name in names:
            # FIXME: never latinize territory names, this leads to too much ambiguity
            # (e.g. "Shanxi" and "Shaanxi" in China)
            name_norm = normalize_address(name, latinize=False, min_length=1)
            if name_norm is None:
                continue
            target = territory.code.split("-")[-1]
            if name_norm in mapping and mapping[name_norm] != target:
                log.warning(
                    "Duplicate mapping for %s (%r, %s and %s)",
                    name,
                    name_norm,
                    target,
                    mapping[name_norm],
                )  # pragma: no cover
            mapping[name_norm] = target

    unload_module("rigour.data.addresses.data")
    # ordinals data now lives in Rust (via rigour._core.ordinals_dict);
    # no Python module to unload.

    # Longest-form-first ordering so multi-token forms aren't shadowed
    # by single-token prefixes in the alternation.
    forms_sorted = sorted(set(mapping.keys()), key=len, reverse=True)
    pattern = re.compile(
        r"(?<!\w)(%s)(?!\w)" % "|".join(re.escape(f) for f in forms_sorted),
        re.U | re.I,
    )
    # Lowercased-key mapping for the case-insensitive substitution
    # callback. `normalize_address` already casefolds, but keeping the
    # explicit lower() preserves the contract from the pre-inline
    # `Replacer(mapping, ignore_case=True)` shape.
    mapping_ci = {k.lower(): v for k, v in mapping.items()}
    return pattern, mapping_ci


def remove_address_keywords(
    address: str, latinize: bool = False, replacement: str = WS
) -> Optional[str]:
    """Strip common address keywords from a normalised address.

    Removes recognised forms (`"street"`, `"road"`, `"south"`,
    territory names, ordinals, …) by substituting each match with
    `replacement`. Consecutive matches produce consecutive
    `replacement` runs — whitespace is **not** collapsed, so the
    output may contain multi-space gaps. Use
    `normality.squash_spaces` afterwards if a single-space
    output is wanted.

    Input must already be normalised with :func:`normalize_address`
    using the same `latinize` flag — the alias table is built
    against that normalised form.

    Args:
        address: A pre-normalised address string.
        latinize: Must match the flag passed to
            :func:`normalize_address`. Default `False`.
        replacement: String substituted in place of each match.
            Defaults to a single ASCII space.

    Returns:
        The address with recognised keywords removed.
    """
    with resource_lock:
        pattern, _ = _address_replacer(latinize=latinize)
    return pattern.sub(replacement, address)


def shorten_address_keywords(address: str, latinize: bool = False) -> Optional[str]:
    """Shorten common address keywords in a normalised address.

    Replaces recognised forms with their canonical short form
    (`"street"` → `"st"`, `"avenue"` → `"av"`, `"united arab
    emirates"` → `"ae"`, …). Multi-token forms beat single-token
    components via longest-form-first ordering in the alias
    pattern, so country names win over their constituent words.

    Input must already be normalised with :func:`normalize_address`
    using the same `latinize` flag — the alias table is built
    against that normalised form.

    Args:
        address: A pre-normalised address string.
        latinize: Must match the flag passed to
            :func:`normalize_address`. Default `False`.

    Returns:
        The address with recognised keywords shortened. Tokens
        that don't match any alias pass through unchanged.
    """
    pattern, mapping = _address_replacer(latinize=latinize)

    def _sub(match: re.Match[str]) -> str:
        value = match.group(1)
        return mapping.get(value.lower(), value)

    return pattern.sub(_sub, address)
