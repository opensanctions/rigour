import re

REPL = re.compile(r"(\s{2,}|\s,|,{2,}|^,|,$)", re.UNICODE)


def sub_match(match: re.Match) -> str:
    text = match.group()
    if len(text) == 1:
        return ""
    if "," in text:
        return ","
    return " "


def clean_address(full: str) -> str:
    # TODO: there's probably a higher-performance way of doing this via
    # a regex or something.
    while True:
        full, count = REPL.subn(sub_match, full)
        if count == 0:
            break
    return full.strip()
