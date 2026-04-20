"""Tests for rigour.text.normalize.

Two groups:

1. Individual flag/cleanup behaviour — sanity checks that each step does
   what it claims. Mirrors the Rust unit tests in
   `rust/src/text/normalize.rs` via the FFI boundary.
2. A small table-driven test for a realistic stopword-key pipeline
   (`casefold | NFKD | squash_spaces` + `Cleanup.Slug`) with explicit
   expected outputs per input.
"""
import pytest

from rigour.text.normalize import Cleanup, Normalize, normalize


# --- individual flags ---


def test_strip_only() -> None:
    assert normalize("  hi  ", Normalize.STRIP) == "hi"
    assert normalize("hi", Normalize.STRIP) == "hi"
    assert normalize("   ", Normalize.STRIP) is None
    assert normalize("", Normalize.STRIP) is None


def test_casefold() -> None:
    assert normalize("HELLO", Normalize.CASEFOLD) == "hello"
    # ß → ss (Unicode casefold, not lowercase)
    assert normalize("Straße", Normalize.CASEFOLD) == "strasse"


def test_squash_spaces() -> None:
    assert normalize("a   b\t c", Normalize.SQUASH_SPACES) == "a b c"
    assert normalize("  hi  ", Normalize.SQUASH_SPACES) == "hi"


def test_squash_unicode_whitespace() -> None:
    """Unicode White_Space property coverage.

    char::is_whitespace in Rust follows the Unicode White_Space property;
    these assertions pin which characters actually get collapsed. Called
    through the FFI so any marshalling issue with non-ASCII whitespace
    also surfaces here.
    """
    # Tabs, CR, LF, vertical tab, form feed — all collapse.
    assert normalize("a\tb", Normalize.SQUASH_SPACES) == "a b"
    assert normalize("a\n\r b", Normalize.SQUASH_SPACES) == "a b"
    # Non-breaking space (U+00A0) — NOT stripped by str.strip() in many
    # languages; explicit here.
    assert normalize("\u00A0hi\u00A0", Normalize.SQUASH_SPACES) == "hi"
    # Ideographic space (U+3000) — CJK full-width space.
    assert normalize("中\u3000文", Normalize.SQUASH_SPACES) == "中 文"
    # Narrow no-break space (U+202F) — French typography.
    assert normalize("a\u202Fb", Normalize.SQUASH_SPACES) == "a b"
    # Line/paragraph separators (U+2028, U+2029).
    assert normalize("a\u2028b", Normalize.SQUASH_SPACES) == "a b"
    assert normalize("a\u2029b", Normalize.SQUASH_SPACES) == "a b"
    # Mixed run of different whitespace → single ASCII space.
    assert (
        normalize("foo\u00A0\t\u2003\u3000bar", Normalize.SQUASH_SPACES)
        == "foo bar"
    )
    # All-whitespace input becomes None.
    assert normalize("\u00A0\u3000\u2028", Normalize.SQUASH_SPACES) is None


def test_squash_zero_width_space_survives() -> None:
    """U+200B is category Cf (Format), not in the White_Space property.

    squash_spaces leaves it alone. Callers that want it gone must use
    Cleanup.Strong (which replaces Cf with delete).
    """
    assert normalize("a\u200Bb", Normalize.SQUASH_SPACES) == "a\u200Bb"
    # Cleanup.Strong deletes Cf → zero-width space is removed.
    assert (
        normalize("a\u200Bb", Normalize.SQUASH_SPACES, Cleanup.Strong) == "ab"
    )


def test_nfc_recompose() -> None:
    # "e" + combining acute → "é"
    assert normalize("e\u0301", Normalize.NFC) == "é"


def test_nfkd_decompose() -> None:
    assert normalize("é", Normalize.NFKD) == "e\u0301"


# --- cleanup variants ---


def test_cleanup_noop_passthrough() -> None:
    assert normalize("hello, world!", Normalize(0), Cleanup.Noop) == "hello, world!"


def test_cleanup_strong_punctuation_to_whitespace() -> None:
    assert (
        normalize("hello,world", Normalize.SQUASH_SPACES, Cleanup.Strong)
        == "hello world"
    )


def test_cleanup_strong_deletes_combining_marks() -> None:
    # Decomposed: "e" + U+0301
    assert normalize("e\u0301", Normalize(0), Cleanup.Strong) == "e"


def test_cleanup_strong_pure_punctuation_becomes_none() -> None:
    assert normalize("!!!", Normalize.SQUASH_SPACES, Cleanup.Strong) is None


def test_cleanup_slug_keeps_combining_marks() -> None:
    assert normalize("e\u0301", Normalize(0), Cleanup.Slug) == "e\u0301"


def test_cleanup_slug_deletes_controls() -> None:
    # U+0007 is a Cc (Control) character. Slug deletes; Strong would WS.
    assert normalize("a\u0007b", Normalize(0), Cleanup.Slug) == "ab"


# --- None input ---


def test_none_input_returns_none() -> None:
    assert normalize(None, Normalize.STRIP) is None
    assert normalize(None, Normalize.CASEFOLD | Normalize.SQUASH_SPACES) is None


# --- flag composition ---


def test_flags_are_int_flag() -> None:
    # IntFlag supports | and in: useful properties for callers.
    combined = Normalize.CASEFOLD | Normalize.SQUASH_SPACES
    assert Normalize.CASEFOLD in combined
    assert Normalize.SQUASH_SPACES in combined
    assert Normalize.STRIP not in combined


# --- stopword-key pipeline: casefold | NFKD | squash + Cleanup.Slug ---
#
# This is the flag composition callers use to build stopword-style
# comparison keys: case-insensitive, diacritic-decomposing, with
# punctuation / controls folded away under the Slug profile (which
# keeps nonspacing marks). Each row pins one concrete (input,
# expected) — mismatches surface the exact diverging input in pytest's
# parametrize ID rather than through an opaque corpus loop.

_STOPWORD_KEY_FLAGS = Normalize.CASEFOLD | Normalize.NFKD | Normalize.SQUASH_SPACES
_STOPWORD_KEY_CLEANUP = Cleanup.Slug


_STOPWORD_KEY_CASES = [
    ("", None),
    ("   ", None),
    ("hello", "hello"),
    ("  Hello World  ", "hello world"),
    ("Hello,\tWorld!", "hello world"),
    ("HELLO WORLD", "hello world"),
    # ß → ss via casefold (not str.lower).
    ("Straße", "strasse"),
    # NFKD decomposes the diaeresis onto its base letter; Slug keeps
    # nonspacing marks (Mn), so the combining mark survives. Expected
    # value is decomposed: "nai\u0308ve", visually identical to input
    # but one codepoint longer.
    ("na\u00EFve", "nai\u0308ve"),
    # Casefold on Cyrillic.
    ("Владимир", "владимир"),
    # Each diacritic-bearing letter decomposes: á → a + U+0301 (acute),
    # ē → e + U+0304 (macron).
    (
        "Kyri\u00E1kos M\u0113tsot\u00E1k\u0113s",
        "kyria\u0301kos me\u0304tsota\u0301ke\u0304s",
    ),
    ("FUAD ALIYEV", "fuad aliyev"),
    # Control character (Cc) → deleted by Slug cleanup.
    ("a\u0007b", "ab"),
    # Hyphen (Pd) → whitespace under Slug → squashed. é also decomposes.
    ("caf\u00E9-bar", "cafe\u0301 bar"),
]


@pytest.mark.parametrize("inp,expected", _STOPWORD_KEY_CASES)
def test_stopword_key_pipeline(inp: str, expected: str | None) -> None:
    assert normalize(inp, _STOPWORD_KEY_FLAGS, _STOPWORD_KEY_CLEANUP) == expected
