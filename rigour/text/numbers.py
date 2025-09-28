from typing import Optional
import unicodedata


def string_number(text: str) -> float | None:
    """Convert Unicode numeric strings to their numeric values. This handles cases in
    which numbers are given in non-latin scripts."""
    # if not text.isnumeric():
    #     return None

    # Try standard int conversion first (for ASCII digits)
    try:
        return float(text)
    except ValueError:
        pass

    # Handle Unicode numeric characters
    result: Optional[float] = None
    for char in text:
        try:
            value = unicodedata.numeric(char)
            if result is None:
                result = 0.0
            result = result * 10 + value
        except ValueError:
            return None
    return result
