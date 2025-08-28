from hashlib import sha1
from typing import List
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
    substantial: List[str] = []
    text = normalize("NFKD", remove_unsafe_chars(text.lower()))
    for char in text:
        if char.isalnum():
            substantial.append(char)
    text = "".join(substantial)
    return sha1(text.encode(ENCODING)).hexdigest()
