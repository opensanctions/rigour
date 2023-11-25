from rigour.text.scripts import is_latin, is_alpha, is_alphanum
from rigour.text.scripts import is_modern_alphabet


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


def test_is_alpha():
    assert is_alpha("a")
    assert not is_alpha("1")
    assert not is_alpha("😋")


def test_is_alphanum():
    assert is_alphanum("a")
    assert is_alphanum("1")
    assert not is_alphanum("😋")
