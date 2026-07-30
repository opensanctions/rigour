

def normalize_code(code: str) -> str | None:
    code = str(code).casefold().strip()
    if not len(code):
        return None
    return code
