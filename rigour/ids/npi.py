import re
from typing import Optional
from stdnum import luhn

from rigour.ids.common import IdentifierFormat

NPI_RE = re.compile(r"\b(\d{10}|\d{15})\b")
INVALID = ("0000000000", "000000000000000", "808400000000000")


class NPI(IdentifierFormat):
    """National Provider Identifier."""

    TITLE: str = "NPI"
    STRONG: bool = True

    # cf. https://www.johndcook.com/blog/2024/06/26/npi-number/

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given string is a valid NPI."""
        if NPI_RE.match(text) is None:
            return False

        if text in INVALID:
            return False

        if len(text) == 10:
            text = "80840" + text

        return bool(luhn.is_valid(text))

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Normalize the given string to a valid NPI."""
        match = NPI_RE.search(text)
        if match is None:
            return None
        value = match.group(1)
        if cls.is_valid(value) and value not in INVALID:
            return value
        return None
