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
