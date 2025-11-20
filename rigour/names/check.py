from functools import cache
from typing import Sequence, Set
import unicodedata

from rigour.text.dictionary import Normalizer
from rigour.names.tokenize import normalize_name


def is_name(name: str) -> bool:
    """Check if the given string is a name. The string is considered a name if it contains at least
    one character that is a letter (category 'L' in Unicode)."""
    for char in name:
        category = unicodedata.category(char)
        if category[0] == "L":
            return True
    return False


def _load_wordlist(words: Sequence[str], normalizer: Normalizer) -> Set[str]:
    """Load a list of words and normalize them using the provided normalizer."""
    wordlist = set()
    for word in words:
        norm = normalizer(word)
        if norm is not None and len(norm) > 0:
            wordlist.add(norm)
    return wordlist


@cache
def _load_stopwords(normalizer: Normalizer) -> Set[str]:
    """Load the stopwords from the data file and normalize them using the provided normalizer."""
    from rigour.data.names.data import STOPWORDS

    return _load_wordlist(STOPWORDS, normalizer)


def is_stopword(
    form: str, *, normalizer: Normalizer = normalize_name, normalize: bool = False
) -> bool:
    """Check if the given form is a stopword. The stopword list is normalized first.

    Args:
        form (str): The token to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking stopwords.
        normalize (bool): Whether to normalize the form before checking.

    Returns:
        bool: True if the form is a stopword, False otherwise.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    stopwords = _load_stopwords(normalizer)
    return norm_form in stopwords


@cache
def _load_nullwords(normalizer: Normalizer) -> set[str]:
    """Load the nullwords from the data file and normalize them using the provided normalizer."""
    from rigour.data.names.data import NULLWORDS

    return _load_wordlist(NULLWORDS, normalizer)


def is_nullword(
    form: str, *, normalizer: Normalizer = normalize_name, normalize: bool = False
) -> bool:
    """Check if the given form is a nullword. Nullwords are words that imply a missing value, such
    as "none", "not available", "n/a", etc. The nullword list is normalized first.

    Args:
        form (str): The token to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking nullwords.
        normalize (bool): Whether to normalize the form before checking.

    Returns:
        bool: True if the form is a nullword, False otherwise.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    nullwords = _load_nullwords(normalizer)
    return norm_form in nullwords


@cache
def _load_generic_person_names(normalizer: Normalizer) -> Set[str]:
    """Load the generic person names from the data file and normalize them using the provided normalizer."""
    from rigour.data.names.data import GENERIC_PERSON_NAMES

    return _load_wordlist(GENERIC_PERSON_NAMES, normalizer)


def is_generic_person_name(
    form: str, *, normalizer: Normalizer = normalize_name, normalize: bool = False
) -> bool:
    """Check if the given form is a generic person name. Generic person names are t, when used
    on their own as a full name, not meaningful identifiers of an individual. Examples would include the word
    "Muhammed", "Abu Bakr", etc. The generic person name list is normalized first.

    Args:
        form (str): The string to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking generic person names.
        normalize (bool): Whether to normalize the form before checking.

    Returns:
        bool: True if the form is a generic person name, False otherwise.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    generic_names = _load_generic_person_names(normalizer)
    return norm_form in generic_names
