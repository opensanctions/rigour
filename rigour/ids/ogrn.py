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


class GRN(IdentifierFormat):
    """Primary State Registration Number (Russian company registration)."""

    TITLE: str = "OGRN"

    # cf. https://docs.trellix.com/de-DE/bundle/data-loss-prevention-11.10.x-classification-definitions-reference-guide/page/GUID-945B4343-861E-4A57-8E60-8B6028871BA1.html

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given string is a valid OGRN."""
        return OGRN_RE.match(text) is not None

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Normalize the given string to a valid OGRN."""
        match = OGRN_RE.search(text)
        if match is None:
            return None
        return match.group(1)

def validate_grn(grn: str) -> bool:
    if len(grn) not in {13, 15}:
        return False  # Check length for GRN or GRNIP
    registration_type = int(grn[0])
    federal_subject_code = int(grn[3:5])
    
    # Validate registration type
    if registration_type not in VALID_REGISTRATION_TYPES:
        return False
    
    # Validate federal subject code
    if federal_subject_code not in VALID_FEDERAL_SUBJECT_CODES:
        return False
    
    # Validate control digit logic
    return validate_control_digit(grn)

def calculate_control_digit(grn: str) -> int:
    if len(grn) == 13:
        number = int(grn[:12])
        return number % 11 if number % 11 != 10 else 0
    elif len(grn) == 15:
        number = int(grn[:14])
        return number % 13 if number % 13 != 10 else 0
    return -1

def validate_control_digit(grn: str) -> bool:
    if len(grn) == 13:
        control_digit = int(grn[12])
        return control_digit == calculate_control_digit(grn)
    elif len(grn) == 15:
        control_digit = int(grn[14])
        return control_digit == calculate_control_digit(grn)
    return False

def test_grn_validator():
    # Valid GRNs (You should replace these examples with real ones, depending on business logic)
    valid_grn_egryul = "1137847171846"  # An example 13-digit GRN
    # valid_grn_egrip = "1159102022738"  # An example 15-digit GRN

    # Invalid GRNs
    invalid_grn_short = "11677"  # Too short
    invalid_grn_long = "315774600002662123"  # Too long
    invalid_grn_control_digit = "1167746691302"  # Wrong control digit
    invalid_grn_registration_type = "9167746691301"  # Invalid registration type

    assert GRN.is_valid(valid_grn_egryul), "Validation failed for valid ЕГРЮЛ GRN."
    # assert GRN.is_valid(valid_grn_egrip), "Validation failed for valid ЕГРИП GRN."
    
    assert not GRN.is_valid(invalid_grn_short), "Incorrect validation result for short GRN."
    assert not GRN.is_valid(invalid_grn_long), "Incorrect validation result for long GRN."
    assert not GRN.is_valid(invalid_grn_control_digit), "Incorrect validation for control digit."
    assert not GRN.is_valid(invalid_grn_registration_type), "Incorrect validation for registration type."

    # Normalization checks
    assert GRN.normalize(valid_grn_egryul) == valid_grn_egryul, "Normalization failed for ЕГРЮЛ."
    # assert GRN.normalize(valid_grn_egrip) == valid_grn_egrip, "Normalization failed for ЕГРИП."

if __name__ == "__main__":
    test_grn_validator()
    print("All tests passed!")