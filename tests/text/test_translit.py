"""Python-surface coverage for `rigour.text.translit`.

The module is a thin re-export of the PyO3 bindings — these tests
verify that (a) the bindings are actually exported and callable from
Python, and (b) the core semantic cases (per-script transliteration,
Latin Extended handling, non-latinizable pass-through, drop flag,
round-trip ASCII guarantee) behave as documented. Exhaustive coverage
lives on the Rust side; this file is the Python contract check.
"""

import pytest

from rigour.text.translit import maybe_ascii, should_ascii


# --- should_ascii ---


def test_should_ascii_pure_ascii():
    assert should_ascii("Hello")
    assert should_ascii("123-45-6789")
    assert should_ascii("")


def test_should_ascii_latinizable_scripts():
    # Each of the six LATINIZE_SCRIPTS individually admitted.
    assert should_ascii("café")        # Latin w/ diacritic
    assert should_ascii("Владимир")    # Cyrillic
    assert should_ascii("Αθήνα")       # Greek
    assert should_ascii("Միթչել")      # Armenian
    assert should_ascii("ნინო")         # Georgian
    assert should_ascii("김민석")       # Hangul


def test_should_ascii_non_latinizable_scripts():
    assert not should_ascii("中国")       # Han
    assert not should_ascii("بشار")      # Arabic
    assert not should_ascii("สวัสดี")    # Thai
    assert not should_ascii("नमस्ते")     # Devanagari
    assert not should_ascii("שלום")      # Hebrew


def test_should_ascii_mixed_scripts():
    # Latin + Cyrillic — both admitted.
    assert should_ascii("Hello мир")
    # Latin + Han — Han rejects the whole input.
    assert not should_ascii("Tokyo 東京")


def test_should_ascii_vacuous_inputs():
    # text_scripts returns empty for these; should_ascii is
    # vacuously True (no disqualifying script present).
    assert should_ascii("")
    assert should_ascii("   ")
    assert should_ascii("!@#$%")
    assert should_ascii("2024-12-31")


# --- maybe_ascii ---


def test_maybe_ascii_pass_through_ascii():
    assert maybe_ascii("Hello") == "Hello"
    assert maybe_ascii("") == ""
    assert maybe_ascii("2024-12-31") == "2024-12-31"


def test_maybe_ascii_latin_diacritics():
    assert maybe_ascii("café") == "cafe"
    assert maybe_ascii("naïve") == "naive"
    assert maybe_ascii("Zürich") == "Zurich"


def test_maybe_ascii_latin_extended_fallback():
    # Cases that hit the fallback table / CLDR Latin-ASCII pass.
    assert maybe_ascii("weißbier") == "weissbier"
    assert maybe_ascii("Lars Løkke") == "Lars Lokke"
    # U+0138 Kra — the original panic trigger. CLDR convention: ĸ → q.
    out = maybe_ascii("ALAĸSANDRAVIC")
    assert out.isascii()
    assert out.lower() == "alaqsandravic"


def test_maybe_ascii_per_script_transliterators():
    # Output should be ASCII for each of the per-script passes.
    for text in ["Владимир", "Αθήνα", "Միթչել", "ნინო", "김민석"]:
        assert maybe_ascii(text).isascii(), f"{text!r} → {maybe_ascii(text)!r}"


def test_maybe_ascii_cyrillic_recognisable():
    # Smoke: the transliteration is at least vaguely correct shape,
    # not a random mangling. "Владимир" should produce something
    # containing "vladimir" case-insensitively.
    assert "vladimir" in maybe_ascii("Владимир").lower()


def test_maybe_ascii_non_latinizable_default_passthrough():
    # drop=False (default) preserves the original.
    assert maybe_ascii("中国") == "中国"
    assert maybe_ascii("بشار") == "بشار"
    assert maybe_ascii("สวัสดี") == "สวัสดี"


def test_maybe_ascii_non_latinizable_drop_empties():
    # drop=True yields empty string.
    assert maybe_ascii("中国", drop=True) == ""
    assert maybe_ascii("بشار", drop=True) == ""


def test_maybe_ascii_mixed_script_with_latinizable():
    # Latin + Cyrillic — both admitted, whole string transliterates.
    out = maybe_ascii("Hello мир")
    assert out.isascii()
    assert out.startswith("Hello ")


def test_maybe_ascii_mixed_with_rejected_script():
    # Latin + Han — Han rejects, whole string kept or dropped.
    assert maybe_ascii("Tokyo 東京") == "Tokyo 東京"
    assert maybe_ascii("Tokyo 東京", drop=True) == ""


# --- round-trip invariant ---


@pytest.mark.parametrize(
    "text",
    [
        "Hello",
        "café",
        "Zürich",
        "Lars Løkke",
        "Владимир Путин",
        "Αθήνα",
        "Միթչել",
        "ნინო",
        "김민석",
        "ALAĸSANDRAVIC",
        "Hello мир",
        "",
        "   ",
        "2024-12-31",
    ],
)
def test_round_trip_should_ascii_implies_ascii_output(text: str):
    """If `should_ascii(x)` is True, `maybe_ascii(x)` must return ASCII.

    The Rust side has an exhaustive per-codepoint guard
    (`maybe_ascii_latin_roundtrip`); this parametrised version just
    samples realistic inputs from the Python side so any future
    binding drift is caught immediately.
    """
    if should_ascii(text):
        assert maybe_ascii(text).isascii(), (
            f"should_ascii({text!r}) is True "
            f"but maybe_ascii({text!r}) = {maybe_ascii(text)!r} is not ASCII"
        )
