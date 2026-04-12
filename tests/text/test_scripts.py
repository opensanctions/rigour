from rigour.text.scripts import is_latin
from rigour.text.scripts import can_latinize, is_modern_alphabet, is_dense_script


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
    """Georgian: can_latinize=True but is_modern_alphabet=False."""
    geo = "ნინო ბურჯანაძე"
    assert not is_latin(geo)
    assert can_latinize(geo)
    assert not is_modern_alphabet(geo)
    assert not is_dense_script(geo)


def test_scripts_armenian():
    """Armenian: can_latinize=True, but is_modern_alphabet=False (not in LATINIZABLE_CHARS)."""
    arm = "Միթչել Մակքոնել"
    assert not is_latin(arm)
    assert can_latinize(arm)
    assert not is_modern_alphabet(arm)
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
