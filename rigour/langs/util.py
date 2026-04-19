from typing import Optional


def normalize_code(code: str) -> Optional[str]:
    code = str(code).casefold().strip()
    if not len(code):
        return None
    return code
