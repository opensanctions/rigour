import logging
from functools import cache
from typing import Dict, List, Optional
from normality.constants import WS

from rigour.text.dictionary import Replacer
from rigour.util import resource_lock, unload_module

# Import Rust implementation
from rigour._core import normalize_address as _normalize_address_core

log = logging.getLogger(__name__)


def normalize_address(
    address: str, latinize: bool = False, min_length: int = 4
) -> Optional[str]:
    """Normalize the given address string for comparison, in a way that is destructive to
    the ability for displaying it (makes it ugly).

    This function is implemented in Rust for performance.

    Args:
        address: The address to be normalized.
        latinize: Whether to convert non-Latin characters to their Latin equivalents.
        min_length: Minimum length of the normalized address.

    Returns:
        The normalized address, or None if below minimum length.
    """
    return _normalize_address_core(address, latinize, min_length)


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
    from rigour.data.text.ordinals import ORDINALS

    ordinals = [(str(k), v) for k, v in ORDINALS.items()]
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
                        value_norm,
                        repl_norm,
                        mapping[value_norm],
                    )  # pragma: no cover
                mapping[value_norm] = repl_norm

    unload_module("rigour.data.addresses.data")
    unload_module("rigour.data.text.ordinals")
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
    with resource_lock:
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
