import re
from typing import Callable, List, Optional, Tuple

from rigour.ids.common import IdentifierFormat

IMO_RE = re.compile(r"(IMO[\s:.#-]*)?(?<!\d)(\d{5,7})(?!\d)")

Checksum = Callable[[List[int]], bool]


def _vessel_checksum(digits: List[int]) -> bool:
    return sum(d * (7 - i) for i, d in enumerate(digits[:6])) % 10 == digits[6]


def _company_checksum(digits: List[int]) -> bool:
    weights = (8, 6, 4, 2, 9, 7)
    checksum = sum(d * w for d, w in zip(digits, weights))
    return (11 - checksum % 11) % 10 == digits[6]


class IMO(IdentifierFormat):
    """An IMO number for a ship or a shipping company.

    Ship and company IMO numbers are both seven digits but use different check
    digit algorithms; this format admits both. Use
    [is_valid_vessel][rigour.ids.imo.IMO.is_valid_vessel] or
    [is_valid_company][rigour.ids.imo.IMO.is_valid_company] when the value
    must belong to one specific scheme, e.g. when minting scheme-specific
    entity IDs.

    Extraction considers digit runs of five to seven digits, preferring longer
    runs, then runs carrying an `IMO` prefix, then earlier ones; the first
    candidate that passes a checksum wins. Runs shorter than seven digits are
    left-padded with zeros, since data sources commonly strip leading zeros
    from IMO fields. The all-zero value is rejected.
    """

    NAME = "imo"
    TITLE = "IMO"
    STRONG = True

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given text contains a valid IMO number.

        Args:
            text: A string that may contain an IMO number.

        Returns:
            True if an IMO number valid in either checksum scheme can be
            extracted from the text.
        """
        return cls._extract(text, (_vessel_checksum, _company_checksum)) is not None

    @classmethod
    def is_valid_vessel(cls, text: str) -> bool:
        """Determine if the given text contains a valid ship IMO number.

        Args:
            text: A string that may contain an IMO number.

        Returns:
            True if an IMO number valid in the vessel checksum scheme can be
            extracted from the text.
        """
        return cls._extract(text, (_vessel_checksum,)) is not None

    @classmethod
    def is_valid_company(cls, text: str) -> bool:
        """Determine if the given text contains a valid company IMO number.

        Args:
            text: A string that may contain an IMO number.

        Returns:
            True if an IMO number valid in the company checksum scheme can be
            extracted from the text.
        """
        return cls._extract(text, (_company_checksum,)) is not None

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Extract and normalize an IMO number from the given text.

        Args:
            text: A string that may contain an IMO number.

        Returns:
            The number in `IMO0000000` form, or None if the text contains no
            checksum-valid IMO number.
        """
        value = cls._extract(text, (_vessel_checksum, _company_checksum))
        if value is None:
            return None
        return f"IMO{value}"

    @classmethod
    def _extract(cls, text: str, checksums: Tuple[Checksum, ...]) -> Optional[str]:
        matches = sorted(
            IMO_RE.finditer(text),
            key=lambda m: (-len(m.group(2)), m.group(1) is None, m.start()),
        )
        for match in matches:
            value = match.group(2).zfill(7)
            digits = [int(d) for d in value]
            if not any(digits):
                continue
            if any(check(digits) for check in checksums):
                return value
        return None

    @classmethod
    def format(cls, value: str) -> str:
        """Format the given value as an IMO number.

        Args:
            value: A pre-validated IMO number.

        Returns:
            The value with an `IMO` prefix.
        """
        value = value.replace(" ", "")
        if not value.startswith("IMO"):
            value = f"IMO{value}"
        return value
