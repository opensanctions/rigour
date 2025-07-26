import re

from normality.constants import WS

EMOJI_PATTERN = re.compile(
    "["
    # Emojis
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f3fb-\U0001f3ff"  # skin tones
    "\Ufe0e\Ufe0f" # variation selectors (these allow emoji and non-emoji forms of the same symbol to be selected)
    # Symbols, shapes, and pictographs 
    "\U0001f9c0-\U0001f9ff"  # additional symbols
    "\U00002700-\U000027bf"  # dingbats
    "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    "\U0001f300-\U0001f5ff"  # symbols and pictographs
    "\U2600-\U26ff" # miscellaneous symbols block (including warning signs and symbols re weather, games, astrology and religion/culture)
    "\U0001f680-\U0001f6ff"  # transport and map symbols
    "\U2b00-\U2bff" # miscellaneous symbols and arrows
    "\U1f650-\U1f67f" # ornamental dingbats
    "\U1f700-\U1f77f" # alchemical symbols
    "\U1f780-\U1f7ff" # geometric shapes extended
    "\U1f900-\U1f9ff" # supplemental symbols and pictographs
    # Mathematical, computing and technical symbols 
    "\U2190-\U21ff" # arrows
    "\U2300-\U23ff" # miscellaneous technical
    "\U2400-\U243f" # control pictures
    "\U2440-\U245f" # optical character recognition
    "\U2500-\U257f" # box drawing
    "\U2580-\U259f" # block elements
    "\U25a0-\U25ff" # geometric shapes
    "\U2a00-\U2aff" # supplemental mathematical operators
    "\U0001FB00-\U0001FBFF" # symbols for legacy computing
    # Games, music, and esoteric symbols 
    "\U4dc0-\U4dff" # Yijing hexagram symbols
    "\U1d100-\U1d1ff" # musical symbols
    "\U1d300-\U1d35f" # Tai Xuan Jing symbols
    "\U1d360-\U1d37f" # counting rod numerals (used in ancient China, Japan, Korea, and Vietnam)
    "\U1f000-\U1f02f" # Mahjong tiles
    "\U1f030-\U1f09f" # domino tiles
    "\U1f0a0-\U1f0ff" # playing cards
    # Ancient/obsolete scripts 
    "\U16a0-\U16ff" # Runic
    "\U1680-\U169f" # Ogham
    "\U10330-\U1034f" # Gothic
    "\U10900-\U1091f" # Phoenician
    "\U10380-\U1039f" # Ugaritic (an extinct Semitic language)
    "\U103a0-\U103df" # Old Persian
    "\U10000-\U100ff" # Linear B (used for an form of the Greek language)
    "\U12000-\U123ff" # Cuneiform
    "\U13000-\U1342f" # Egyptian hieroglyphs
    "\U14400-\U1467f" # Anatolian hieroglyphs
    # Constructed languages/scripts 
    "\U10450-\U1047f" # Shavian (constructed script created in the 1950s and 1960s to write English)
    "\U10400-\U1044f" # Deseret (developed in the 19th century by the Mormon Church for English)
    "\U11a00-\U11a4f" # Zanabazar square script (17th century script for Tibetan and Sanskrit, now decorative)
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
