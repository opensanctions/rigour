import re
from functools import cache

from rigour._core import name_split_phrases_list


def name_split_phrases() -> list[str]:
    """List the alias-marker phrases that separate names in one string.

    Reach for this when a caller needs the raw markers (`"a.k.a."`,
    `"f/k/a"`, `"dba"`, ...), e.g. to split or classify a multi-name
    string itself; use
    [contains_split_phrase][rigour.names.contains_split_phrase] for a
    plain yes/no check. Phrases come from
    `resources/names/stopwords.yml::NAME_SPLIT_PHRASES`.

    Returns:
        A fresh list of phrases in their resource spelling (mixed case).
    """
    return name_split_phrases_list()


@cache
def _split_phrase_regex() -> re.Pattern[str]:
    """Compile the split-phrase regex from the Rust-owned wordlist."""
    patterns = [re.escape(phrase) for phrase in name_split_phrases_list()]
    pattern = rf"(\b({'|'.join(patterns)})\b)"
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def contains_split_phrase(string: str) -> bool:
    """Check whether `string` contains an alias-marker phrase.

    Detects markers like `"a.k.a."`, `"f.k.a."`, `"née"`, `"alias"`,
    that signal a single string actually carries multiple distinct
    names. Useful for triaging input — a string with a split
    phrase shouldn't be treated as one atomic name. The phrase
    list is data-driven from
    `resources/names/stopwords.yml::NAME_SPLIT_PHRASES`, listed by
    [name_split_phrases][rigour.names.name_split_phrases].

    Args:
        string: An input that may contain one or more names.

    Returns:
        `True` iff at least one split-phrase marker appears in
        `string` as a whole word.
    """
    return _split_phrase_regex().search(string) is not None
