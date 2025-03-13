from typing import List


def clean_code(code: str) -> str:
    """Clean up a territory code."""
    return code.lower().replace("_", "-").strip()


def clean_codes(codes: List[str]) -> List[str]:
    """Clean up a list of territory codes."""
    return [clean_code(code) for code in codes if len(clean_code(code)) > 1]
