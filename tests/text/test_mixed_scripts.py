"""Mixed-script regression tests.

Exercises the Rust-backed `text_scripts`, `ascii_text`, `latinize_text`, and
the predicate family against realistic combinations of two or more scripts.
The previous test suite (`test_transliteration.py`) still imports from
`normality`, which pins PyICU output but doesn't exercise the Rust path we
actually ship. This file imports from the rigour modules directly so it
catches regressions in the Rust implementation.
"""

from rigour.text.scripts import (
    can_latinize,
    is_dense_script,
    is_latin,
    is_modern_alphabet,
    text_scripts,
)
from rigour.text.transliteration import ascii_text, latinize_text


# --- text_scripts: detection across combinations --------------------------


def test_text_scripts_two_non_latin() -> None:
    """Two non-Latin scripts, no Latin, no whitespace — sanity-check that
    text_scripts still splits them despite the missing separator."""
    assert text_scripts("Москва北京") == {"Cyrillic", "Han"}


def test_text_scripts_latin_plus_diacritics_only() -> None:
    """Latin with diacritics should still resolve to just {Latin}."""
    assert text_scripts("François Müller") == {"Latin"}


def test_text_scripts_four_scripts() -> None:
    """Four scripts in one string — an unrealistic but boundary-useful input."""
    # Hebrew + Arabic + Hangul + Latin
    assert text_scripts("שלום سلام 안녕 Hello") == {
        "Hebrew",
        "Arabic",
        "Hangul",
        "Latin",
    }


def test_text_scripts_ignores_numbers_and_punctuation() -> None:
    """Common-script characters don't show up as 'Common' in the result."""
    # All of these are Common — digits, punctuation, whitespace.
    assert text_scripts("2024-12-31 09:42:07") == set()


def test_text_scripts_transition_without_whitespace() -> None:
    """Bilingual compound names where scripts collide mid-token."""
    assert text_scripts("Tokyo東京") == {"Latin", "Han"}
    assert text_scripts("Smith-Петров") == {"Latin", "Cyrillic"}


# --- ascii_text: end-to-end transliteration of mixed inputs ---------------


def test_ascii_text_latin_plus_cyrillic() -> None:
    out = ascii_text("Vladimir Путин")
    assert out.isascii()
    assert "Vladimir" in out
    # The Cyrillic half should yield a Putin-ish romanisation.
    assert "utin" in out.lower()


def test_ascii_text_latin_diacritics_plus_han() -> None:
    """A name mixing French diacritics with Chinese. The diacritic side
    decomposes via NFKD; the Han side goes through the Pinyin transliterator."""
    out = ascii_text("José 习近平")
    assert out.isascii()
    assert out.startswith("Jose")
    # The Han half should contribute non-empty ASCII letters after the space.
    tail = out.split(" ", 1)[1] if " " in out else out
    assert any(c.isalpha() for c in tail)


def test_ascii_text_three_scripts() -> None:
    out = ascii_text("Hello мир 中国")
    assert out.isascii()
    assert out.lower().startswith("hello ")


def test_ascii_text_adjacent_scripts_no_whitespace() -> None:
    """No space between script transitions — transliterator boundaries
    should still work."""
    out = ascii_text("Tokyo東京")
    assert out.isascii()
    assert "Tokyo" in out


def test_ascii_text_unsupported_script_passthrough() -> None:
    """Thai is not in ICU4X compiled_data. Mixed input should keep the
    Latin portion transliterated-or-unchanged and leave the Thai alone."""
    out = ascii_text("Hello สวัสดี")
    assert out.startswith("Hello ")
    # Thai characters survive because we have no transliterator for them.
    assert "ส" in out


def test_ascii_text_pure_punctuation_and_numbers() -> None:
    """No script-bearing characters → no transliteration work to do."""
    assert ascii_text("2024-12-31 !@#$") == "2024-12-31 !@#$"
    assert ascii_text("") == ""


# --- latinize_text: Latin output preserving diacritics --------------------


def test_latinize_text_preserves_latin_diacritics() -> None:
    assert latinize_text("François Müller") == "François Müller"


def test_latinize_text_mixed_latin_and_cyrillic() -> None:
    out = latinize_text("Sergei Сергей")
    # Must contain the ASCII Sergei on one side; Cyrillic gone from the other.
    assert "Sergei" in out
    assert not any("\u0400" <= c <= "\u04FF" for c in out)


def test_latinize_text_adjacent_scripts_no_whitespace() -> None:
    out = latinize_text("Tokyo東京")
    # Han letters should all be gone; Latin prefix intact.
    assert "Tokyo" in out
    assert not any("\u4E00" <= c <= "\u9FFF" for c in out)


def test_latinize_text_unsupported_script_passthrough() -> None:
    """Thai + Latin: Latin stays, Thai passes through untransliterated."""
    out = latinize_text("Hello สวัสดี")
    assert out.startswith("Hello ")
    assert "ส" in out


# --- Predicates on mixed-script inputs ------------------------------------


def test_predicates_latin_plus_cyrillic() -> None:
    mixed = "Hello мир"
    assert not is_latin(mixed)
    assert can_latinize(mixed)  # both scripts are in LATINIZE_SCRIPTS
    assert is_modern_alphabet(mixed)  # both scripts are modern alphabets
    assert not is_dense_script(mixed)


def test_predicates_latin_plus_han() -> None:
    mixed = "Tokyo東京"
    assert not is_latin(mixed)
    assert not can_latinize(mixed)  # Han isn't in LATINIZE_SCRIPTS
    assert not is_modern_alphabet(mixed)
    assert is_dense_script(mixed)  # Han triggers dense


def test_predicates_latin_plus_hangul() -> None:
    """Hangul is both latinizable and dense — unusual overlap."""
    mixed = "Kim 김민석"
    assert not is_latin(mixed)
    assert can_latinize(mixed)
    assert is_dense_script(mixed)  # Hangul counts as dense


def test_predicates_pure_punctuation() -> None:
    """No script-bearing chars — predicates fall out to vacuously True on
    subset-style checks, False on intersection-style checks."""
    punct = "2024-12-31 !@#$"
    assert is_latin(punct)  # vacuously — text_scripts returns empty set
    assert is_modern_alphabet(punct)
    assert can_latinize(punct)
    assert not is_dense_script(punct)
