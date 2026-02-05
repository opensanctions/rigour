from rigour.text.scripts import is_latin, get_script
from rigour.text.scripts import can_latinize, is_modern_alphabet


def test_get_script() -> None:
    # Test basic Latin
    assert get_script(ord("A")) == "Latin"
    assert get_script(ord("z")) == "Latin"
    # Test Cyrillic
    assert get_script(ord("Б")) == "Cyrillic"
    # Test Greek
    assert get_script(ord("α")) == "Greek"
    # Test Han (Chinese)
    assert get_script(ord("日")) == "Han"
    # Test Hangul (Korean)
    assert get_script(ord("가")) == "Hangul"
    # Test Hiragana (Japanese)
    assert get_script(ord("あ")) == "Hiragana"
    # Test Armenian
    assert get_script(ord("Ա")) == "Armenian"
    # Test Arabic
    assert get_script(ord("ع")) == "Arabic"
    # Test codepoint that's not in any range
    assert get_script(0) is None
    # Test codepoint between ranges (control character)
    assert get_script(1) is None


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
