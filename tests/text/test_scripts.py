from rigour.text.scripts import codepoint_script, text_scripts, common_scripts
from rigour.text.scripts import is_latin
from rigour.text.scripts import can_latinize, can_latinize_cp
from rigour.text.scripts import is_modern_alphabet, is_dense_script


def test_codepoint_script_basic():
    assert codepoint_script(ord("A")) == "Latin"
    assert codepoint_script(ord("а")) == "Cyrillic"
    assert codepoint_script(ord("中")) == "Han"
    assert codepoint_script(ord("가")) == "Hangul"
    assert codepoint_script(ord("Α")) == "Greek"
    assert codepoint_script(ord("Ա")) == "Armenian"
    assert codepoint_script(ord("ა")) == "Georgian"


def test_codepoint_script_common_inherited():
    # codepoint_script is a faithful Unicode lookup — Common and Inherited
    # are returned as-is rather than filtered out.
    assert codepoint_script(ord(" ")) == "Common"
    assert codepoint_script(ord("0")) == "Common"
    assert codepoint_script(0x0301) == "Inherited"  # combining acute
    assert codepoint_script(0xD800) is None  # lone surrogate


def test_text_scripts_mixed():
    assert text_scripts("Hello, мир! 中文 123") == {"Latin", "Cyrillic", "Han"}
    assert text_scripts("") == set()
    assert text_scripts("123 !@#") == set()  # Common-only input → empty set
    assert text_scripts("Hello") == {"Latin"}
    assert text_scripts("你好") == {"Han"}


def test_can_latinize_cp():
    assert can_latinize_cp(ord("A")) is True
    assert can_latinize_cp(ord("а")) is True  # Cyrillic
    assert can_latinize_cp(ord("中")) is False
    # Non-alphanumeric or no real script → None
    assert can_latinize_cp(ord(" ")) is None
    assert can_latinize_cp(ord("0")) is None  # digit — Common script
    assert can_latinize_cp(ord("!")) is None


def test_is_latin():
    assert is_latin("banana")
    assert not is_latin("банан")
    assert is_latin("😋"), ord("😋")


def test_is_modern_alphabet():
    assert is_modern_alphabet("banana")
    assert is_modern_alphabet("банан")
    assert not is_modern_alphabet("中國哲學書電子化計劃")
    assert not is_modern_alphabet("ᚠ")
    assert is_modern_alphabet("😋")  # skips irrelevant blocks


def test_can_latinize():
    assert can_latinize("banana")
    assert can_latinize("банан")
    assert not can_latinize("中國哲學書電子化計劃")
    assert not can_latinize("ᚠ")
    assert can_latinize("😋")  # skips irrelevant blocks


def test_is_dense_script():
    assert is_dense_script("习近平")  # Xi Jinping - Han (Simplified Chinese)
    assert is_dense_script("習近平")  # Xi Jinping - Han (Traditional Chinese)
    assert is_dense_script("高市早苗")  # Sanae Takaichi - Han (Japanese kanji)
    assert is_dense_script("ひらがな")  # Hiragana
    assert is_dense_script("カタカナ")  # Katakana
    assert is_dense_script("東京Tokyo")  # mixed Han + Latin
    assert is_dense_script("김민석")  # Kim Min-seok - Hangul (Korean)
    assert not is_dense_script("banana")
    assert not is_dense_script("банан")  # Cyrillic
    assert not is_dense_script("😋")  # skips irrelevant blocks


# --- Latin-script languages with diacritics ---


def test_scripts_spanish():
    assert is_latin("María García López")
    assert can_latinize("María García López")
    assert not is_dense_script("María García López")
    assert is_modern_alphabet("María García López")


def test_scripts_portuguese():
    assert is_latin("Luiz Inácio Lula da Silva")
    assert is_latin("António Guterres")


def test_scripts_scandinavian():
    assert is_latin("Göran Persson")       # Swedish ö
    assert is_latin("Lars Løkke Rasmussen") # Danish ø
    assert is_latin("Sauli Niinistö")       # Finnish ö


def test_scripts_baltic():
    assert is_latin("Dalia Grybauskeitė")  # Lithuanian ė
    assert is_latin("Kersti Kaljulaid")          # Estonian


def test_scripts_hungarian():
    assert is_latin("Orbán Viktor")
    assert is_latin("Szijjártó Péter")


def test_scripts_dutch():
    assert is_latin("Jan Peter van der Berg")


def test_scripts_polish():
    assert is_latin("Małgorzata Gersdorf")  # ł


def test_scripts_turkish():
    assert is_latin("Recep Tayyip Erdoğan")  # ğ
    assert is_latin("Süleyman Şahin")    # Ş


# --- Non-Latin scripts ---


def test_scripts_georgian():
    """Georgian is both latinizable and a modern alphabet.

    Behaviour change from the pre-Rust-port implementation: previously
    is_modern_alphabet(georgian) returned False because the underlying
    LATINIZABLE_CHARS set only held Latin+Cyrillic+Greek, contradicting the
    docstring's intent to include Armenian and Georgian. The set-based
    rewrite aligns code with docstring.
    """
    geo = "ნინო ბურჯანაძე"
    assert not is_latin(geo)
    assert can_latinize(geo)
    assert is_modern_alphabet(geo)
    assert not is_dense_script(geo)


def test_scripts_armenian():
    """Armenian is both latinizable and a modern alphabet. See test_scripts_georgian
    for the behaviour-change rationale."""
    arm = "Միթչել Մակքոնել"
    assert not is_latin(arm)
    assert can_latinize(arm)
    assert is_modern_alphabet(arm)
    assert not is_dense_script(arm)


# --- Boundary codepoints ---


def test_scripts_boundary_codepoints():
    """Test codepoints at script boundaries."""
    # Last basic Latin (U+007A = z)
    assert is_latin("z")
    # Latin Extended-A (U+0100)
    assert is_latin("Ā")
    # First Cyrillic (U+0400)
    assert not is_latin("Ѐ")
    assert can_latinize("Ѐ")
    assert is_modern_alphabet("Ѐ")
    # Georgian (U+10D0)
    assert not is_latin("ა")
    assert can_latinize("ა")
    # Hangul syllable (U+AC00)
    assert not is_latin("가")
    assert can_latinize("가")
    assert is_dense_script("가")
    # CJK Unified Ideograph (U+4E00)
    assert not can_latinize("一")
    assert is_dense_script("一")


# --- Mixed scripts: text_scripts detection ---


def test_text_scripts_two_non_latin():
    """Two non-Latin scripts, no Latin, no whitespace — text_scripts still
    splits them despite the missing separator."""
    assert text_scripts("Москва北京") == {"Cyrillic", "Han"}


def test_text_scripts_latin_plus_diacritics_only():
    """Latin with diacritics should still resolve to just {Latin}."""
    assert text_scripts("François Müller") == {"Latin"}


def test_text_scripts_four_scripts():
    """Four scripts in one string — an unrealistic but boundary-useful input."""
    # Hebrew + Arabic + Hangul + Latin
    assert text_scripts("שלום سلام 안녕 Hello") == {
        "Hebrew",
        "Arabic",
        "Hangul",
        "Latin",
    }


def test_text_scripts_ignores_numbers_and_punctuation():
    """Common-script characters don't show up as 'Common' in the result."""
    assert text_scripts("2024-12-31 09:42:07") == set()


def test_text_scripts_transition_without_whitespace():
    """Bilingual compound names where scripts collide mid-token."""
    assert text_scripts("Tokyo東京") == {"Latin", "Han"}
    assert text_scripts("Smith-Петров") == {"Latin", "Cyrillic"}


# --- Mixed scripts: predicates ---


def test_predicates_latin_plus_cyrillic():
    mixed = "Hello мир"
    assert not is_latin(mixed)
    assert can_latinize(mixed)  # both scripts are in LATINIZE_SCRIPTS
    assert is_modern_alphabet(mixed)  # both are modern alphabets
    assert not is_dense_script(mixed)


def test_predicates_latin_plus_han():
    mixed = "Tokyo東京"
    assert not is_latin(mixed)
    assert not can_latinize(mixed)  # Han isn't in LATINIZE_SCRIPTS
    assert not is_modern_alphabet(mixed)
    assert is_dense_script(mixed)  # Han triggers dense


def test_predicates_latin_plus_hangul():
    """Hangul is both latinizable and dense — unusual overlap."""
    mixed = "Kim 김민석"
    assert not is_latin(mixed)
    assert can_latinize(mixed)
    assert is_dense_script(mixed)


def test_predicates_pure_punctuation():
    """No script-bearing chars — predicates fall out to vacuously True on
    subset-style checks, False on intersection-style checks."""
    punct = "2024-12-31 !@#$"
    assert is_latin(punct)  # vacuously — text_scripts returns empty set
    assert is_modern_alphabet(punct)
    assert can_latinize(punct)
    assert not is_dense_script(punct)


# --- common_scripts ---


def test_common_scripts_both_latin():
    assert common_scripts("Hello", "World") == {"Latin"}


def test_common_scripts_disjoint_latin_han():
    assert common_scripts("Hello", "你好") == set()
    assert common_scripts("你好", "Hello") == set()


def test_common_scripts_mixed_both_sides():
    # Both contain Latin + Han — intersection preserves both.
    assert common_scripts("Hello 你好", "Tokyo 東京") == {"Latin", "Han"}


def test_common_scripts_partial_overlap():
    # Query has Latin + Cyrillic, candidate has Cyrillic only.
    assert common_scripts("Hello мир", "Владимир") == {"Cyrillic"}


def test_common_scripts_numbers_only():
    # Pure Common on both sides → empty intersection.
    assert common_scripts("007", "123") == set()


def test_common_scripts_punctuation_only():
    assert common_scripts("!@#", "...") == set()


def test_common_scripts_numbers_vs_latin():
    # One pure-Common side → no real scripts to intersect.
    assert common_scripts("007", "Hello") == set()
    assert common_scripts("Hello", "007") == set()


def test_common_scripts_empty_inputs():
    assert common_scripts("", "") == set()
    assert common_scripts("", "Hello") == set()
    assert common_scripts("Hello", "") == set()


def test_common_scripts_never_returns_pseudo_scripts():
    # Even when both strings are loaded with Common/Inherited
    # codepoints, neither is a valid return value.
    out = common_scripts("2024 !@# 1-2", "!!! ... ???")
    assert "Common" not in out
    assert "Inherited" not in out
    assert out == set()
