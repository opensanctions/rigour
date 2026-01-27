from hashlib import sha1
from unicodedata import normalize
from normality.cleaning import remove_unsafe_chars

from rigour.env import ENCODING


def text_hash(text: str) -> str:
    """Generate a hash for the given text, ignoring whitespace and punctuation.

    Args:
        text (str): The input text to hash.

    Returns:
        str: The SHA-1 hash of the processed text.
    """
    text = normalize("NFKD", remove_unsafe_chars(text.lower()))
    substantial = [c for c in text if c.isalnum()]
    text = "".join(substantial)
    return sha1(text.encode(ENCODING)).hexdigest()
