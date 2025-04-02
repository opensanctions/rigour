import re

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


# https://stackoverflow.com/a/49146722/330558
def remove_emoji(string: str) -> str:
    return EMOJI_PATTERN.sub(r"", string)
