import unicodedata


def string_number(text: str) -> float | None:
    """Convert Unicode numeric strings to their numeric values. This handles cases in
    which numbers are given in non-latin scripts."""
    if not text.isnumeric():
        return None

    # Try standard int conversion first (for ASCII digits)
    try:
        return float(text)
    except ValueError:
        pass

    # Handle Unicode numeric characters
    result = 0.0
    for char in text:
        value = unicodedata.numeric(char, None)
        if value is not None:
            result = result * 10 + value
    return result
