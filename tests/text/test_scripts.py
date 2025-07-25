from rigour.text.scripts import is_latin
from rigour.text.scripts import can_latinize, is_modern_alphabet


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
