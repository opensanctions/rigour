import re
from functools import cache

from rigour._core import name_split_phrases_list


@cache
def _split_phrase_regex() -> re.Pattern[str]:
    """Compile the split-phrase regex from the Rust-owned wordlist."""
    patterns = [re.escape(phrase) for phrase in name_split_phrases_list()]
    pattern = rf"(\b({'|'.join(patterns)})\b)"
    return re.compile(pattern, re.I | re.U)


def contains_split_phrase(string: str) -> bool:
    """Check whether `string` contains an alias-marker phrase.

    Detects markers like `"a.k.a."`, `"f.k.a."`, `"née"`, `"alias"`,
    that signal a single string actually carries multiple distinct
    names. Useful for triaging input — a string with a split
    phrase shouldn't be treated as one atomic name. The phrase
    list is data-driven from
    `resources/names/stopwords.yml::NAME_SPLIT_PHRASES`,
    surfaced via `rigour._core.name_split_phrases_list`.

    Args:
        string: An input that may contain one or more names.

    Returns:
        `True` iff at least one split-phrase marker appears in
        `string` as a whole word.
    """
    return _split_phrase_regex().search(string) is not None
