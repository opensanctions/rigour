import re
from typing import Optional

from rigour.ids.common import IdentifierFormat

IMO_RE = re.compile(r"\b(IMO)?(\d{7})\b")


class IMO(IdentifierFormat):
    """An IMO number for a ship or shipping company"""

    TITLE = "IMO"
    STRONG: bool = True

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given string is a valid IMO number."""
        match = IMO_RE.search(text)
        if match is None:
            return False
        value = match.group(2)
        digits = [int(d) for d in value]

        # Check if it's a vessel IMO number:
        checksum = sum(d * (7 - i) for i, d in enumerate(digits[:-1])) % 10
        if checksum == digits[-1]:
            return True

        # Check if it's a company IMO number:
        checksum = digits[0] * 8 + digits[1] * 6 + digits[2] * 4
        checksum += +digits[3] * 2 + digits[4] * 9 + digits[5] * 7
        checksum = (11 - (checksum % 11)) % 10
        if checksum == digits[-1]:
            return True

        return False

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Normalize the given string to a valid NPI."""
        match = IMO_RE.search(text)
        if match is None:
            return None
        value = match.group(2)
        if cls.is_valid(value):
            return f"IMO{value}"
        return None

    @classmethod
    def format(cls, value: str) -> str:
        value = value.replace(" ", "")
        if not value.startswith("IMO"):
            value = f"IMO{value}"
        return value
