from functools import cache
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


@cache
def _load_stopwords(normalizer: Normalizer) -> set[str]:
    """Load the stopwords from the data file and normalize them using the provided normalizer."""
    from rigour.data.names.data import STOPWORDS

    stopwords = set()
    for word in STOPWORDS:
        norm = normalizer(word)
        if norm is not None and len(norm) > 0:
            stopwords.add(norm)
    return stopwords


def is_stopword(form: str, normalizer: Normalizer = normalize_name) -> bool:
    """Check if the given form is a stopword. The stopword list is normalized first.

    Args:
        form (str): The token to check, must already be normalized.
        normalizer (Normalizer): The normalizer to use for checking stopwords.

    Returns:
        bool: True if the form is a stopword, False otherwise.
    """
    stopwords = _load_stopwords(normalizer)
    return form in stopwords
