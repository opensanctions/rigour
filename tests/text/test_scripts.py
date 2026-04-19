from rigour.text.scripts import codepoint_script, text_scripts
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
