from functools import cache
from typing import Sequence, Set
import unicodedata
import warnings

from rigour.text.normalize import Normalizer
from rigour.names.tokenize import normalize_name

# Re-export stopword and nullword functions from rigour.text.stopwords for backwards compatibility
from rigour.text.stopwords import is_stopword as _is_stopword
from rigour.text.stopwords import is_nullword as _is_nullword


def is_name(name: str) -> bool:
    """Check whether `name` plausibly contains a name.

    Loose filter — true iff at least one character is a Unicode
    letter (general category `L*`). Useful for rejecting purely
    numeric (`"007"`) or punctuation-only (`"---"`) inputs before
    handing them to the rest of the name pipeline.

    Args:
        name: A string.

    Returns:
        `True` iff `name` contains at least one letter.
    """
    for char in name:
        category = unicodedata.category(char)
        if category[0] == "L":
            return True
    return False


def is_stopword(
    form: str, *, normalizer: Normalizer = normalize_name, normalize: bool = False
) -> bool:
    """Check if the given form is a stopword. The stopword list is normalized first.

    .. deprecated::
        Use :func:`rigour.text.is_stopword` instead. This function will be removed in a future version.

    Args:
        form (str): The token to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking stopwords.
        normalize (bool): Whether to normalize the form before checking.

    Returns:
        bool: True if the form is a stopword, False otherwise.
    """
    warnings.warn(
        "rigour.names.is_stopword is deprecated, use rigour.text.is_stopword instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return _is_stopword(form, normalizer=normalizer, normalize=normalize)


def is_nullword(
    form: str, *, normalizer: Normalizer = normalize_name, normalize: bool = False
) -> bool:
    """Check if the given form is a nullword. Nullwords are words that imply a missing value, such
    as "none", "not available", "n/a", etc. The nullword list is normalized first.

    .. deprecated::
        Use :func:`rigour.text.is_nullword` instead. This function will be removed in a future version.

    Args:
        form (str): The token to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking nullwords.
        normalize (bool): Whether to normalize the form before checking.

    Returns:
        bool: True if the form is a nullword, False otherwise.
    """
    warnings.warn(
        "rigour.names.is_nullword is deprecated, use rigour.text.is_nullword instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return _is_nullword(form, normalizer=normalizer, normalize=normalize)


def _load_wordlist(words: Sequence[str], normalizer: Normalizer) -> Set[str]:
    """Load a list of words and normalize them using the provided normalizer."""
    wordlist = set()
    for word in words:
        norm = normalizer(word)
        if norm is not None and len(norm) > 0:
            wordlist.add(norm)
    return wordlist


@cache
def _load_generic_person_names(normalizer: Normalizer) -> Set[str]:
    """Load the generic person names from the data file and normalize them using the provided normalizer."""
    from rigour._core import generic_person_names_list

    return _load_wordlist(generic_person_names_list(), normalizer)


def is_generic_person_name(
    form: str, *, normalizer: Normalizer = normalize_name, normalize: bool = False
) -> bool:
    """Check whether `form` is a generic given/family name.

    Generic person names are common forms that, used on their own
    as a full name, don't meaningfully identify an individual —
    `"Muhammed"`, `"John"`, `"Maria"`, etc. Useful for flagging
    records where the alias slot was populated with a single
    generic name rather than a discriminating one.

    Both the wordlist and runtime input must be normalised with
    the same `normalizer` for the membership check to be
    meaningful.

    Args:
        form: The string to check.
        normalizer: Normalizer applied to the wordlist at load
            time, and to `form` when `normalize=True`.
        normalize: When `True`, run `normalizer(form)` before the
            lookup. When `False` (default), `form` is assumed to
            be pre-normalised.

    Returns:
        `True` iff the (possibly normalised) form is in the
        generic-person-names list.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    generic_names = _load_generic_person_names(normalizer)
    return norm_form in generic_names
