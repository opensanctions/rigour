from functools import lru_cache
from typing import Optional

from rigour._core import codepoint_script as _codepoint_script
from rigour._core import common_scripts as _common_scripts
from rigour._core import text_scripts as _text_scripts
from rigour.util import MEMO_MEDIUM


#: Scripts whose romanisation is well-defined enough that
#: rigour will automatically transliterate them to ASCII via
#: :func:`rigour.text.translit.maybe_ascii`.
LATINIZE_SCRIPTS = {"Hangul", "Cyrillic", "Greek", "Armenian", "Latin", "Georgian"}

#: Letter-based writing systems with explicit vowels — these
#: transliterate reliably to Latin without language hints.
#: Excludes Hangul (syllabic) and the dense logographic scripts.
MODERN_ALPHABETS = {"Latin", "Cyrillic", "Greek", "Armenian", "Georgian"}

#: Scripts denser than Latin: more meaning or sound per codepoint.
#: Hangul is included because it encodes syllables, not individual
#: sounds. Useful as a rough proxy for "doesn't use whitespace to
#: separate name parts" — though Hangul actually does use spaces.
#: https://en.wikipedia.org/wiki/List_of_writing_systems#Logographic_systems
DENSE_SCRIPTS = {"Han", "Hiragana", "Katakana", "Hangul"}


@lru_cache(maxsize=MEMO_MEDIUM)
def codepoint_script(cp: int) -> Optional[str]:
    """Return the Unicode Script long name for a codepoint.

    Faithful exposure of the Unicode Script property via ICU4X.
    Returns the pseudo-scripts `"Common"` (digits, punctuation,
    spaces) and `"Inherited"` (combining marks) as-is — callers
    that want to filter them out should do so explicitly via
    :func:`text_scripts`, which already does.

    Args:
        cp: Codepoint as an integer. Accepts any `u32` value
            including surrogates and unassigned codepoints, so
            callers can pass `ord(c)` of any character without a
            `TypeError` at the FFI boundary.

    Returns:
        Script long name (`"Latin"`, `"Cyrillic"`, `"Han"`,
        `"Common"`, `"Inherited"`, …), or `None` for unassigned
        or invalid codepoints (including lone surrogates).
    """
    return _codepoint_script(cp)


def text_scripts(text: str) -> set[str]:
    """Return the set of distinct real scripts present in text.

    The right primitive for *"which writing systems does this
    string use?"*. Only letters (General_Category `L*`) and
    numbers (`N*`) contribute; Common, Inherited, and Unknown are
    excluded — shared characters (digits, punctuation) and
    combining marks don't count as their own script.

    Args:
        text: Any string, including empty.

    Returns:
        Set of script long names. Empty when the input has no
        letters or numbers (numeric-only, punctuation-only,
        empty).
    """
    return _text_scripts(text)


def common_scripts(a: str, b: str) -> set[str]:
    """Return the scripts both strings have in common.

    Equivalent to ``text_scripts(a) & text_scripts(b)``. Cheap
    pruning predicate — two strings that share no real script
    have no textual bridge unless both are individually
    latinizable.

    The empty-result caveat is the main subtlety. An empty return
    is ambiguous between *"scripts are disjoint"* (e.g. Latin vs
    Han) and *"one side has no real scripts"* (numeric-only,
    punctuation-only, empty). The two cases have different
    matching implications — a numeric-only name like `"007"` can
    still match `"Agent 007"` via shared `NUMERIC` symbols even
    though `common_scripts` is empty. Pruning callers should
    treat empty-script inputs as wildcards that bypass the script
    gate, falling through to symbol-overlap or scoring. Callers
    that need to distinguish the two cases should call
    :func:`text_scripts` on each side explicitly.

    Args:
        a: A string.
        b: Another string.

    Returns:
        Intersection of the two strings' real-script sets.
    """
    return _common_scripts(a, b)


@lru_cache(maxsize=MEMO_MEDIUM)
def can_latinize_cp(cp: int) -> Optional[bool]:
    """Check whether a single codepoint can be latinized.

    Three-valued: distinguishing-script-bearing codepoints get a
    True/False; others (digits, punctuation, combining marks)
    return `None` because the question doesn't apply to them.

    Args:
        cp: Codepoint as an integer.

    Returns:
        `True` if the codepoint's script is in
        :data:`LATINIZE_SCRIPTS`, `False` if it has a real script
        outside that set, `None` for non-alphanumeric or
        Common/Inherited/Unknown codepoints.
    """
    char = chr(cp)
    if not char.isalnum():
        return None
    script = codepoint_script(cp)
    if script is None or script in ("Common", "Inherited"):
        return None
    return script in LATINIZE_SCRIPTS


def can_latinize(word: str) -> bool:
    """Check whether every script in a word is latinizable.

    Equivalent to `text_scripts(word) <= LATINIZE_SCRIPTS`. When
    True, :func:`rigour.text.translit.maybe_ascii` will produce
    an ASCII output; when False, it returns the input unchanged.
    Characters with no distinguishing script (digits, punctuation,
    spaces, combining marks) are ignored. Empty input and
    pure-Common input (`"123"`) return True vacuously.

    Args:
        word: A string.

    Returns:
        True iff every distinguishing script is in
        :data:`LATINIZE_SCRIPTS`.
    """
    return text_scripts(word) <= LATINIZE_SCRIPTS


def is_modern_alphabet(word: str) -> bool:
    """Check whether a word uses only modern alphabets.

    Modern alphabets (Latin, Cyrillic, Greek, Armenian, Georgian)
    are letter-based systems with explicit vowels that
    transliterate reliably to Latin without language hints.
    Excludes Hangul (syllabic) and the dense logographic scripts.

    Args:
        word: A string.

    Returns:
        True iff every distinguishing script is in
        :data:`MODERN_ALPHABETS`. Pure-ASCII input short-circuits
        to True without script detection.
    """
    if word.isascii():
        return True
    return text_scripts(word) <= MODERN_ALPHABETS


def is_latin(word: str) -> bool:
    """Check whether a word is written in the Latin alphabet only.

    Args:
        word: A string.

    Returns:
        True iff the only distinguishing script in `word` is
        Latin. Pure-ASCII input short-circuits to True.
    """
    if word.isascii():
        return True
    return text_scripts(word) <= {"Latin"}


def is_dense_script(word: str) -> bool:
    """Check whether a word uses any dense (logographic or
    syllabic) script.

    Rough proxy for "doesn't use whitespace to separate name
    parts" — though Hangul actually does use spaces, it's still
    grouped here because it encodes syllables rather than
    individual sounds.

    Args:
        word: A string.

    Returns:
        True iff `word` contains any character whose script is
        in :data:`DENSE_SCRIPTS`.
    """
    return bool(text_scripts(word) & DENSE_SCRIPTS)
