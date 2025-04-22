import unicodedata


def is_name(name: str) -> bool:
    """Check if the given string is a name. The string is considered a name if it contains at least
    one character that is a letter (category 'L' in Unicode)."""
    for char in name:
        category = unicodedata.category(char)
        if category[0] == "L":
            return True
    return False
