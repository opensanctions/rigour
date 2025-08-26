import pytest

from rigour.langs.text import LangStr


def test_langstr():
    # Test creation without language
    text = LangStr("Hello")
    assert text == "Hello"
    assert text.lang is None
    assert repr(text) == repr("Hello")

    # Test creation with language
    text = LangStr("Hello", lang="eng")
    assert text == "Hello"
    assert text.lang == "eng"

    # Test representation
    text = LangStr("Hello", lang="eng")
    assert repr(text) == '"Hello"@eng'

    assert "Hello" == text
    assert hash(text) == hash(("Hello", "eng"))
    assert text != LangStr("Hello", lang="deu")

    with pytest.raises(ValueError):
        LangStr("Hello", lang="invalid")
