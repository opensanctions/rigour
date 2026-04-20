import unicodedata
from typing import List
from normality import latinize_text, squash_spaces

from rigour.text.scripts import can_latinize_cp

SKIP_CHARACTERS = ".()[],;:_-/ʻ'’"


def clean_code(code: str) -> str:
    """Clean up a territory code."""
    return code.lower().replace("_", "-").strip()


def clean_codes(codes: List[str]) -> List[str]:
    """Clean up a list of territory codes."""
    return [clean_code(code) for code in codes if len(clean_code(code)) > 1]


def normalize_territory_name(name: str) -> str:
    """Normalize a territory name for lookup."""
    name = unicodedata.normalize("NFKD", name).casefold()
    can_latinize = True
    filtered: List[str] = []
    for char in name:
        if char in SKIP_CHARACTERS:
            continue
        if not char.isalnum():
            filtered.append(" ")
            continue
        cp = ord(char)
        if not can_latinize_cp(cp):
            can_latinize = False
        filtered.append(char)
    normalized = "".join(filtered)
    if can_latinize:
        normalized = latinize_text(normalized)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = squash_spaces(normalized)
    return normalized
