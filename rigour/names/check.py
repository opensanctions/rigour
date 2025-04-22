import unicodedata


def is_name(name: str) -> bool:
    """Check if the given string is a name."""
    for char in name:
        category = unicodedata.category(char)
        if category[0] == "L":
            return True
    return False
