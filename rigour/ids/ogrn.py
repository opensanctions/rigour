import re
from typing import Optional

from rigour.ids.common import IdentifierFormat

OGRN_RE = re.compile(r"\b(\d{13}|\d{15})\b")

# Constants representing federal subject codes and registration types
VALID_FEDERAL_SUBJECT_CODES = set(range(1, 80)) | {83, 86, 87, 89, 91, 92, 99}
VALID_REGISTRATION_TYPES = {1, 2, 3, 4, 5, 6, 7, 8, 9}


class OGRN(IdentifierFormat):
    """Primary State Registration Number (Russian company registration)."""

    TITLE: str = "OGRN"

    # cf. https://docs.trellix.com/de-DE/bundle/data-loss-prevention-11.10.x-classification-definitions-reference-guide/page/GUID-945B4343-861E-4A57-8E60-8B6028871BA1.html

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given string is a valid OGRN."""
        if OGRN_RE.match(text) is None:
            return False

        if len(text) not in {13, 15}:
            return False  # Check length for GRN or GRNIP

        registration_type = int(text[0])
        federal_subject_code = int(text[3:5])

        # Validate registration type
        if registration_type not in VALID_REGISTRATION_TYPES:
            return False

        # Validate federal subject code
        if federal_subject_code not in VALID_FEDERAL_SUBJECT_CODES:
            return False

        # Validate control digit logic
        return cls.validate_control_digit(text)

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Normalize the given string to a valid OGRN."""
        match = OGRN_RE.search(text)
        if match is None:
            return None
        return match.group(1)

    @classmethod
    def calculate_control_digit(cls, grn: str) -> Optional[int]:
        if len(grn) == 13:
            number = int(grn[:12])
            mod_result = number % 11
            calculated_digit = mod_result if mod_result != 10 else 0
            print(f"GRN (13 digits): {grn}, Number: {number}, Mod 11: {mod_result}")
            return calculated_digit
        elif len(grn) == 15:
            number = int(grn[:14])
            mod_result = number % 13
            calculated_digit = mod_result if mod_result != 10 else 0
            print(f"GRN (15 digits): {grn}, Number: {number}, Mod 13: {mod_result}")
            return calculated_digit
        return None

    @classmethod
    def validate_control_digit(cls, grn: str) -> bool:
        if len(grn) == 13:
            control_digit = int(grn[12])
            print(f"Control digit: {control_digit}")
            return control_digit == cls.calculate_control_digit(grn)
        elif len(grn) == 15:
            control_digit = int(grn[14])
            print(f"Control digit: {control_digit}")
            return control_digit == cls.calculate_control_digit(grn)
        return False
