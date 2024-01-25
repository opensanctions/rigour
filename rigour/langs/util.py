from typing import Optional


def normalize_code(code: str) -> Optional[str]:
    code = str(code)
    code = code.lower().strip()
    if not len(code):
        return None
    return code
