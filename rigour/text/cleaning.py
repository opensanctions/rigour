import re

from normality.constants import WS

EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    "\u2600-\u26ff"
    "\U0001f680-\U0001f6ff"  # transport & map symbols
    "\U00002700-\U000027bf"  # dingbats
    "\ufe0e\ufe0f"
    "\U0001f3fb-\U0001f3ff"  # skin tones
    "\U0001f9c0-\U0001f9ff"  # additional symbols
    "]+",
    flags=re.UNICODE,
)

BRACKETED = re.compile(r"(\([^\(\)]*\)|\[[^\[\]]*\]|\（[^\(\）]*）)", re.UNICODE)


# https://stackoverflow.com/a/49146722/330558
def remove_emoji(string: str) -> str:
    """Remove unicode ranges used by emoticons, symbolks, flags and other visual codepoints from
    a piece of text. Primary use case is to remove shit emojis from the names of political office
    holders coming from Wikidata.

    Args:
        string: Text that may include emoji and pictographs.

    Returns:
        Text that doesn't include those.
    """
    return EMOJI_PATTERN.sub(r"", string)


def remove_bracketed_text(text: str) -> str:
    """Remove any text in brackets. This is meant to handle names of companies
    which include the jurisdiction, like: Turtle Management (Seychelles) Ltd.

    Args:
        text: A text including text in brackets.

    Returns:
        Text where this has been substituted for whitespace.
    """
    return BRACKETED.sub(WS, text)
