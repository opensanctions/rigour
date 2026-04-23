from functools import lru_cache
from typing import Optional

from rigour._core import codepoint_script as _codepoint_script
from rigour._core import common_scripts as _common_scripts
from rigour._core import text_scripts as _text_scripts
from rigour.util import MEMO_MEDIUM


# Scripts rigour considers safe to latinize via automated transliteration.
LATINIZE_SCRIPTS = {"Hangul", "Cyrillic", "Greek", "Armenian", "Latin", "Georgian"}

# Modern alphabets: letter-based systems that transliterate reliably to Latin.
# Previously (pre-Rust migration) this family excluded Armenian and Georgian due
# to a gap between the docstring intent and the LATINIZABLE_CHARS set the code
# actually checked. The new set-based implementation aligns with the docstring.
MODERN_ALPHABETS = {"Latin", "Cyrillic", "Greek", "Armenian", "Georgian"}

# Scripts that are denser than Latin (fewer code points per unit of
# meaning/sound). Includes Hangul along with logographic scripts because it
# encodes syllables rather than individual sounds.
# https://en.wikipedia.org/wiki/List_of_writing_systems#Logographic_systems
DENSE_SCRIPTS = {"Han", "Hiragana", "Katakana", "Hangul"}


@lru_cache(maxsize=MEMO_MEDIUM)
def codepoint_script(cp: int) -> Optional[str]:
    """Return the Unicode Script long name for a codepoint.

    Returns "Common" for codepoints like digits, punctuation, and spaces;
    "Inherited" for combining marks; the script name (e.g. "Latin", "Cyrillic",
    "Han") for script-bearing codepoints; and None only for unassigned /
    invalid codepoints (including lone surrogates).

    This is a faithful exposure of the Unicode Script property via ICU4X. It
    differs from the previous `get_script` behaviour (which filtered Common
    and Inherited out) — if callers need that filter, they should apply it
    explicitly.
    """
    return _codepoint_script(cp)


def text_scripts(text: str) -> set[str]:
    """Return the set of distinct script long names present in text.

    Only letters (General_Category L*) and numbers (N*) contribute; Common,
    Inherited, and Unknown scripts are excluded from the result. This makes
    `text_scripts` the right primitive for "which writing systems does this
    string use?" questions — shared characters (digits, punctuation) and
    combining marks don't count as their own script.
    """
    return _text_scripts(text)


def common_scripts(a: str, b: str) -> set[str]:
    """Return the scripts both strings have in common.

    Equivalent to ``text_scripts(a) & text_scripts(b)`` — only real scripts
    from Letter/Number codepoints; Common, Inherited, and Unknown are never
    returned.

    **Empty-result caveat.** An empty return is ambiguous: it can mean
    "scripts are disjoint" (e.g. Latin vs Han) *or* "one side has no real
    scripts" (numeric-only, punctuation-only, empty). The two cases have
    different matching implications — a numeric-only name like "007" can
    still match "Agent 007" via shared NUMERIC symbols even though
    `common_scripts` is empty. Pruning callers should guard this: treat
    empty-script inputs as wildcards that bypass the script gate and fall
    through to symbol-overlap or scoring. Callers that need to distinguish
    the two cases should call `text_scripts` on each side explicitly.
    """
    return _common_scripts(a, b)


@lru_cache(maxsize=MEMO_MEDIUM)
def can_latinize_cp(cp: int) -> Optional[bool]:
    """Check if a codepoint should be latinized.

    Returns None for non-alphanumeric codepoints and for those with no
    distinguishing script (Common, Inherited, Unknown). Returns True if the
    codepoint's script is in LATINIZE_SCRIPTS, False otherwise.
    """
    char = chr(cp)
    if not char.isalnum():
        return None
    script = codepoint_script(cp)
    if script is None or script in ("Common", "Inherited"):
        return None
    return script in LATINIZE_SCRIPTS


def can_latinize(word: str) -> bool:
    """Check if a word should be latinized using automated transliteration.

    Returns True when every distinguishing script in the word is in
    LATINIZE_SCRIPTS. Characters with no distinguishing script (digits,
    punctuation, spaces, combining marks) are ignored. Empty input and
    pure-Common input (e.g. "123") return True vacuously.
    """
    return text_scripts(word) <= LATINIZE_SCRIPTS


def is_modern_alphabet(word: str) -> bool:
    """Check if a word uses only modern alphabets.

    Modern alphabets are letter-based systems with vowels that transliterate
    reliably to Latin: Latin, Cyrillic, Greek, Armenian, Georgian.
    """
    if word.isascii():
        return True
    return text_scripts(word) <= MODERN_ALPHABETS


def is_latin(word: str) -> bool:
    """Check if a word is written in the Latin alphabet."""
    if word.isascii():
        return True
    return text_scripts(word) <= {"Latin"}


def is_dense_script(word: str) -> bool:
    """Check if a word contains characters from a script that is notably denser
    than Latin: one that encodes more meaning/sound per Unicode codepoint.

    This can be a rough proxy for scripts which don't use spaces to separate
    names, although it includes Hangul which does use spaces to separate words.
    """
    return bool(text_scripts(word) & DENSE_SCRIPTS)
