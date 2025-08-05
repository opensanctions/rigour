import re

from normality.constants import WS

RANGE_PATTERN = re.compile(
    "["
    # Emojis
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f3fb-\U0001f3ff"  # skin tones
    "\ufe0e-\ufe0f"  # variation selectors (these allow emoji and non-emoji forms of the same symbol to be selected)
    # Symbols, shapes, and pictographs
    "\U00002700-\U000027bf"  # dingbats
    "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    "\U0001f300-\U0001f5ff"  # symbols and pictographs (range also includes skin tones which is also covered above)
    "\U00002600-\U000026ff"  # miscellaneous symbols block (including warning signs and symbols re weather, games, astrology and religion/culture)
    "\U0001f680-\U0001f6ff"  # transport and map symbols
    "\U00002b00-\U00002bff"  # miscellaneous symbols and arrows
    "\U0001f650-\U0001f67f"  # ornamental dingbats
    "\U0001f700-\U0001f77f"  # alchemical symbols
    "\U0001f780-\U0001f7ff"  # geometric shapes extended
    "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
    # Musical symbols
    "\U0001d100-\U0001d1ff"  # musical symbols
    "\U0001d200-\U0001d24f"  # Ancient Greek musical notation
    "\U0001d000-\U0001d0ff"  # Byzantine musical symbols
    "\U0001cf00-\U0001cfcf"  # Znamenny musical notation
    # Mathematical, computing and technical symbols
    "\U00002190-\U000021ff"  # arrows
    "\U00002300-\U000023ff"  # miscellaneous technical
    "\U00002400-\U0000243f"  # control pictures
    "\U00002440-\U0000245f"  # optical character recognition
    "\U00002500-\U0000257f"  # box drawing
    "\U00002580-\U0000259f"  # block elements
    "\U000025a0-\U000025ff"  # geometric shapes
    "\U00002200-\U000022ff"  # mathematical operators and symbols
    "\U00002a00-\U00002aff"  # supplemental mathematical operators
    "\U0001fb00-\U0001fbff"  # symbols for legacy computing
    # Symbols used for games
    "\U0001f000-\U0001f02f"  # Mahjong tiles
    "\U0001f030-\U0001f09f"  # domino tiles
    "\U0001f0a0-\U0001f0ff"  # playing cards
    # Shorthand
    "\U0001bc00-\U0001bc9f"  # Duployan shorthand
    # Unicode specials block
    "\ufff0-\uffff"  # character for encoding errors (�) etc
    "]+",
    flags=re.UNICODE,
)

BRACKETED = re.compile(r"(\([^\(\)]*\)|\[[^\[\]]*\]|\（[^\(\）]*）)", re.UNICODE)


# https://stackoverflow.com/a/49146722/330558
def remove_emoji(string: str) -> str:
    """Remove unicode ranges used by emoticons, symbols, flags and other visual codepoints from
    a piece of text. Primary use case is to remove shit emojis from the names of political office
    holders coming from Wikidata.

    Args:
        string: Text that may include emoji and pictographs.

    Returns:
        Text that doesn't include those.
    """
    return RANGE_PATTERN.sub(r"", string)


def remove_bracketed_text(text: str) -> str:
    """Remove any text in brackets. This is meant to handle names of companies
    which include the jurisdiction, like: Turtle Management (Seychelles) Ltd.

    Args:
        text: A text including text in brackets.

    Returns:
        Text where this has been substituted for whitespace.
    """
    return BRACKETED.sub(WS, text)
