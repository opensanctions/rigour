from functools import cache
from typing import Optional


def bool_text(value: Optional[bool]) -> Optional[str]:
    """Convert a boolean value to a string representation. If the input is None, it returns
    None. If the input is True, it returns 't'. If the input is False, it returns 'f'."""
    if value is None:
        return None
    return "t" if value else "f"


@cache
def text_bool(text: Optional[str]) -> Optional[bool]:
    """Convert a string representation of a boolean value to a boolean. If the input is None
    or an empty string, it returns None."""
    if text is None or len(text) == 0:
        return None
    text = text.lower()
    return text.startswith("t") or text.startswith("y") or text.startswith("1")
