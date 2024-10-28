import re
from typing import Optional

from rigour.ids.common import IdentifierFormat

OGRN_RE = re.compile(r"\b(\d{13}|\d{15})\b")

# Constants representing federal subject codes and registration types
VALID_FEDERAL_SUBJECT_CODES = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
    17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
    31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44,
    45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58,
    59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72,
    73, 74, 75, 76, 77, 78, 79, 83, 86, 87, 89, 91, 92, 99
}
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
    def calculate_control_digit(cls, grn: str) -> int:
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
        return -1

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