from functools import cache
from typing import Optional, Sequence, Set

from normality import category_replace, squash_spaces
from normality.constants import SLUG_CATEGORIES
from rigour.text.dictionary import Normalizer


def normalize_text(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = text.casefold()
    replaced = category_replace(text, SLUG_CATEGORIES)
    replaced = squash_spaces(replaced)
    return replaced if len(replaced) > 0 else None


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
    from rigour.data.text.stopwords import STOPWORDS

    return _load_wordlist(STOPWORDS, normalizer)


def is_stopword(
    form: str, *, normalizer: Normalizer = normalize_text, normalize: bool = False
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
    from rigour.data.text.stopwords import NULLWORDS

    return _load_wordlist(NULLWORDS, normalizer)


def is_nullword(
    form: str, *, normalizer: Normalizer = normalize_text, normalize: bool = False
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
def _load_nullplaces(normalizer: Normalizer) -> set[str]:
    """Load the nullplaces from the data file and normalize them using the provided normalizer."""
    from rigour.data.text.stopwords import NULLPLACES

    return _load_wordlist(NULLPLACES, normalizer)


def is_nullplace(
    form: str, *, normalizer: Normalizer = normalize_text, normalize: bool = False
) -> bool:
    """Check if the given form is a nullplace. Nullplaces are place names that don't refer to a
    specific location, such as "overseas", "abroad", "stateless", etc. The nullplace list is
    normalized first.

    Args:
        form (str): The string to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking nullplaces.
        normalize (bool): Whether to normalize the form before checking.

    Returns:
        bool: True if the form is a nullplace, False otherwise.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    nullplaces = _load_nullplaces(normalizer)
    return norm_form in nullplaces
