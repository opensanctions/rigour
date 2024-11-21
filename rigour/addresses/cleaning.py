import re

REPL = re.compile(r"(\s{2,}|\s,|,{2,}|^[,\s]|[,\s]$)", re.UNICODE)


def _sub_match(match: re.Match[str]) -> str:
    text = match.group()
    if len(text) == 1:
        return ""
    if "," in text:
        return ","
    return " "


def clean_address(full: str) -> str:
    """Remove common formatting errors from addresses."""
    while True:
        full, count = REPL.subn(_sub_match, full)
        if count == 0:
            break
    return full.strip()
