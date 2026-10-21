import unicodedata

from normality import squash_spaces

from rigour.text.scripts import can_latinize
from rigour.text.translit import ascii_text

SKIP_CHARACTERS = ".()[],;:_-/ʻ'’"


def clean_code(code: str) -> str:
    """Clean up a territory code."""
    return code.lower().replace("_", "-").strip()


def clean_codes(codes: list[str]) -> list[str]:
    """Clean up a list of territory codes."""
    return [clean_code(code) for code in codes if len(clean_code(code)) > 1]


def normalize_territory_name(name: str) -> str:
    """Normalize a territory name for lookup.

    Transliterates the scripts [ascii_text][rigour.text.translit.ascii_text]
    handles natively to ASCII, casefolds, drops punctuation and squashes
    whitespace, so that `São Tomé`, `Sao Tome` and `SAO TOME` all key
    identically. Other scripts keep their letters and marks.

    Args:
        name: A territory name or alias in any script.

    Returns:
        The normalized lookup key.
    """
    if can_latinize(name):
        name = ascii_text(name)
    name = unicodedata.normalize("NFKC", name).casefold()
    filtered: list[str] = []
    for char in name:
        if char in SKIP_CHARACTERS:
            continue
        # Combining marks carry vowels in e.g. Devanagari; turning them into
        # spaces would split the word.
        if not char.isalnum() and not unicodedata.category(char).startswith("M"):
            filtered.append(" ")
            continue
        filtered.append(char)
    return squash_spaces("".join(filtered))
