from functools import cache
from typing import Optional, Sequence, Set

from normality import category_replace, squash_spaces
from normality.constants import SLUG_CATEGORIES

from rigour._core import nullplaces_list, nullwords_list, stopwords_list
from rigour.text.normalize import Normalizer, noop_normalizer


def normalize_text(text: Optional[str]) -> Optional[str]:
    """Default normalizer for stopword / nullword / nullplace lookup.

    Composes casefold + slug-category replacement + whitespace
    squash. Used as the default :data:`Normalizer` for the three
    lookup predicates below; callers must apply the same
    normaliser to runtime input as the one used to load the
    wordlist for membership checks to be consistent.

    Args:
        text: Input string, or `None`.

    Returns:
        Normalised string, or `None` when input is `None` or
        normalisation produces an empty string.
    """
    if text is None:
        return None
    text = text.casefold()
    replaced = category_replace(text, SLUG_CATEGORIES)
    replaced = squash_spaces(replaced)
    return replaced if len(replaced) > 0 else None


def _load_wordlist(words: Sequence[str], normalizer: Normalizer) -> Set[str]:
    """Apply `normalizer` to every word and return the non-empty
    results as a set. Internal builder used by the per-list
    `_load_*` helpers below."""
    wordlist = set()
    for word in words:
        norm = normalizer(word)
        if norm is not None and len(norm) > 0:
            wordlist.add(norm)
    return wordlist


@cache
def _load_stopwords(normalizer: Normalizer) -> Set[str]:
    """Build the stopword set using `normalizer`. Cached so the
    same `(normalizer, wordlist)` combination is built once per
    process."""
    return _load_wordlist(stopwords_list(), normalizer)


def is_stopword(
    form: str, *, normalizer: Normalizer = normalize_text, normalize: bool = False
) -> bool:
    """Check whether `form` is a stopword.

    Stopwords are common words that carry no identifying signal
    in name-matching contexts (`"the"`, `"and"`, `"of"`, etc.).
    Both the wordlist and the runtime input must be normalised
    with the same `normalizer` for the membership check to be
    meaningful.

    Args:
        form: The token to check.
        normalizer: Normalizer applied to the wordlist at load
            time, and to `form` when `normalize=True`.
        normalize: When `True`, run `normalizer(form)` before the
            lookup. When `False` (default), `form` is assumed to
            be pre-normalised by the caller.

    Returns:
        `True` iff the (possibly normalised) form is in the
        stopword list.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    stopwords = _load_stopwords(normalizer)
    return norm_form in stopwords


@cache
def _load_nullwords(normalizer: Normalizer) -> set[str]:
    """Build the nullword set using `normalizer`. Cached per
    `(normalizer, wordlist)`."""
    return _load_wordlist(nullwords_list(), normalizer)


def is_nullword(
    form: str, *, normalizer: Normalizer = normalize_text, normalize: bool = False
) -> bool:
    """Check whether `form` is a nullword.

    Nullwords are tokens that imply a missing value:
    `"none"`, `"not available"`, `"n/a"`, `"unknown"`, etc.
    Useful for filtering out records where an alias slot was
    populated with a placeholder rather than real data.

    Args:
        form: The token to check.
        normalizer: Normalizer applied to the wordlist at load
            time, and to `form` when `normalize=True`.
        normalize: When `True`, run `normalizer(form)` before the
            lookup. When `False` (default), `form` is assumed to
            be pre-normalised.

    Returns:
        `True` iff the (possibly normalised) form is in the
        nullword list.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    nullwords = _load_nullwords(normalizer) if normalize else _load_nullwords(noop_normalizer)
    return norm_form in nullwords


@cache
def _load_nullplaces(normalizer: Normalizer) -> set[str]:
    """Build the nullplace set using `normalizer`. Cached per
    `(normalizer, wordlist)`."""
    return _load_wordlist(nullplaces_list(), normalizer)


def is_nullplace(
    form: str, *, normalizer: Normalizer = normalize_text, normalize: bool = False
) -> bool:
    """Check whether `form` is a nullplace.

    Nullplaces are place names that don't refer to a specific
    location: `"overseas"`, `"abroad"`, `"stateless"`,
    `"international waters"`, etc. Useful for filtering out
    records where a country / address slot was populated with a
    placeholder rather than a real geography.

    Args:
        form: The string to check.
        normalizer: Normalizer applied to the wordlist at load
            time, and to `form` when `normalize=True`.
        normalize: When `True`, run `normalizer(form)` before the
            lookup. When `False` (default), `form` is assumed to
            be pre-normalised.

    Returns:
        `True` iff the (possibly normalised) form is in the
        nullplace list.
    """
    norm_form = normalizer(form) if normalize else form
    if norm_form is None:
        return False
    nullplaces = _load_nullplaces(normalizer)
    return norm_form in nullplaces
