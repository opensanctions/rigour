import re

from normality.constants import WS

EMOJI_PATTERN = re.compile(
    "["
    # Emojis
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f3fb-\U0001f3ff"  # skin tones
    "\ufe0e-\ufe0f" # variation selectors (these allow emoji and non-emoji forms of the same symbol to be selected)
    # Symbols, shapes, and pictographs 
    "\U00002700-\U000027bf"  # dingbats
    "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    "\U0001f300-\U0001f5ff"  # symbols and pictographs (range also includes skin tones which is also covered above)
    "\U0002600-\U00026ff" # miscellaneous symbols block (including warning signs and symbols re weather, games, astrology and religion/culture)
    "\U0001f680-\U0001f6ff"  # transport and map symbols
    "\U0002b00-\U0002bff" # miscellaneous symbols and arrows
    "\U0001f650-\U0001f67f" # ornamental dingbats
    "\U0001f700-\U0001f77f" # alchemical symbols
    "\U0001f780-\U0001f7ff" # geometric shapes extended
    "\U0001f900-\U0001f9ff" # supplemental symbols and pictographs
    # Mathematical, computing and technical symbols 
    "\U0002190-\U00021ff" # arrows
    "\U0002300-\U00023ff" # miscellaneous technical
    "\U0002400-\U000243f" # control pictures
    "\U0002440-\U000245f" # optical character recognition
    "\U0002500-\U000257f" # box drawing
    "\U0002580-\U000259f" # block elements
    "\U00025a0-\U00025ff" # geometric shapes
    "\U0002200-\U00022ff" # mathematical operators and symbols
    "\U0002a00-\U0002aff" # supplemental mathematical operators
    "\U0001FB00-\U0001FBFF" # symbols for legacy computing
    # Games, music, and esoteric symbols 
    "\U0004dc0-\U0004dff" # Yijing hexagram symbols
    "\U0001d100-\U0001d1ff" # musical symbols
    "\U0001d300-\U0001d35f" # Tai Xuan Jing symbols
    "\U0001d360-\U0001d37f" # counting rod numerals (used in ancient China, Japan, Korea, and Vietnam)
    "\U0001f000-\U0001f02f" # Mahjong tiles
    "\U0001f030-\U0001f09f" # domino tiles
    "\U0001f0a0-\U0001f0ff" # playing cards
    # Shorthand
    "\U0001BC00-\U0001BC9f" # Duployan shorthand
    # Unicode specials block
    "\ufff0-\uffff" # character for encoding errors (�) etc
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
