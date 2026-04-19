"""Tests for rigour.text.normalize.

Two groups:

1. Basic flag/cleanup behaviour — sanity checks that each step does what
   it claims. Mirrors the Rust unit tests in rust/src/text/normalize.rs
   via the FFI boundary.

2. Parity against legacy normalizers — for each existing
   `normalize_*` function in rigour, assert that an equivalent flag
   composition produces the same output on a small corpus. This is the
   evidence that the callback-pattern replacement is safe to roll out.
"""
from rigour.names.org_types import normalize_display, _normalize_compare
from rigour.text.normalize import Cleanup, Normalize, normalize
from rigour.text.stopwords import normalize_text


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


def test_latinize() -> None:
    out = normalize("Владимир", Normalize.LATINIZE)
    assert out is not None
    # No Cyrillic characters remain
    assert not any("\u0400" <= c <= "\u04FF" for c in out)


def test_ascii() -> None:
    out = normalize("Владимир", Normalize.ASCII)
    assert out is not None
    assert out.isascii()


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


# --- parity with legacy normalizers ---

# A small corpus covering the quirks of each legacy function. Each entry
# is an input string that probes a distinct normalization concern.
_PARITY_CORPUS = [
    "",
    "   ",
    "hello",
    "  Hello World  ",
    "Hello,\tWorld!",
    "HELLO WORLD",
    "Straße",
    "naïve",
    "Владимир",
    "Kyriákos Mētsotákēs",
    "FUAD ALIYEV",
    "a\u0007b",               # control character
    "café-bar",
]


def test_parity_normalize_display() -> None:
    # normalize_display: squash_spaces (keeps case, no cleanup)
    flags = Normalize.STRIP | Normalize.SQUASH_SPACES
    for inp in _PARITY_CORPUS:
        legacy = normalize_display(inp)
        rust = normalize(inp, flags, Cleanup.Noop)
        assert legacy == rust, (
            f"normalize_display divergence on {inp!r}: "
            f"legacy={legacy!r}, rust={rust!r}"
        )


def test_parity_normalize_compare() -> None:
    # _normalize_compare: squash_spaces → casefold
    flags = Normalize.STRIP | Normalize.CASEFOLD | Normalize.SQUASH_SPACES
    for inp in _PARITY_CORPUS:
        legacy = _normalize_compare(inp)
        rust = normalize(inp, flags, Cleanup.Noop)
        assert legacy == rust, (
            f"_normalize_compare divergence on {inp!r}: "
            f"legacy={legacy!r}, rust={rust!r}"
        )


def test_parity_normalize_text_stopwords() -> None:
    # normalize_text: casefold → category_replace(SLUG) → squash_spaces
    # Note: normality.category_replace secretly applies NFKD before the
    # lookup; our flag model makes that explicit. Callers migrating from
    # `normalize_text` to the flag API must include NFKD to preserve
    # byte-for-byte output on precomposed inputs like "naïve".
    flags = Normalize.CASEFOLD | Normalize.NFKD | Normalize.SQUASH_SPACES
    for inp in _PARITY_CORPUS:
        legacy = normalize_text(inp)
        rust = normalize(inp, flags, Cleanup.Slug)
        assert legacy == rust, (
            f"normalize_text divergence on {inp!r}: "
            f"legacy={legacy!r}, rust={rust!r}"
        )
