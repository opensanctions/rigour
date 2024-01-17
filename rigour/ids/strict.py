from typing import Optional
from normality.transliteration import ascii_text

from rigour.ids.common import IdentifierFormat


class StrictFormat(IdentifierFormat):
    """A generic identifier type that applies harsh normalization."""

    TITLE: str = "Strict identifier"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        norm = cls.normalize(value)
        return norm is not None and len(norm) > 2

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        ascii = ascii_text(value)
        if ascii is None or len(ascii) < 2:
            return None
        chars = [c for c in ascii if c.isalnum()]
        return "".join(chars).upper()
