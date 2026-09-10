import unicodedata

from normality import latinize_text, squash_spaces

from rigour.text.scripts import can_latinize

SKIP_CHARACTERS = ".()[],;:_-/ʻ'’"


def clean_code(code: str) -> str:
    """Clean up a territory code."""
    return code.lower().replace("_", "-").strip()


def clean_codes(codes: list[str]) -> list[str]:
    """Clean up a list of territory codes."""
    return [clean_code(code) for code in codes if len(clean_code(code)) > 1]


def normalize_territory_name(name: str) -> str:
    """Normalize a territory name for lookup.

    Casefolds, drops punctuation, folds accents on Latin, Cyrillic and Greek
    text, and squashes whitespace, so that `São Tomé`, `Sao Tome` and
    `SAO TOME` all key identically.

    Args:
        name: A territory name or alias in any script.

    Returns:
        The normalized lookup key.
    """
    name = unicodedata.normalize("NFKD", name).casefold()
    filtered: list[str] = []
    for char in name:
        if char in SKIP_CHARACTERS:
            continue
        # NFKD splits accents and vowel signs into combining marks, which are
        # not alphanumeric; they must stay attached to their base letter so
        # latinization can fold them instead of a space splitting the word.
        if not char.isalnum() and not unicodedata.category(char).startswith("M"):
            filtered.append(" ")
            continue
        filtered.append(char)
    normalized = "".join(filtered)
    if can_latinize(normalized):
        # Latinized output keeps diacritics (são, rossiâ); fold them so that
        # accented and plain spellings share a key. Scripts that are not
        # latinized keep their marks, which carry vowels in e.g. Devanagari.
        normalized = unicodedata.normalize("NFKD", latinize_text(normalized))
        normalized = "".join(
            char
            for char in normalized
            if not unicodedata.category(char).startswith("M")
        )
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = squash_spaces(normalized)
    return normalized
