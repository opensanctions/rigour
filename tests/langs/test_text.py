import pytest

from rigour.langs.text import LangStr


def test_langstr():
    text = LangStr("Hello")
    assert text == "Hello"
    assert text.lang is None
    assert repr(text) == repr("Hello")

    text = LangStr("Hello", lang="eng")
    assert text.lang == "eng"
    assert repr(text) == '"Hello"@eng'
    assert str(text) == "Hello"

    with pytest.raises(ValueError):
        LangStr("Hello", lang="invalid")


def test_untagged_behaves_like_str():
    text = LangStr("foo")
    assert text == "foo"
    assert "foo" == text
    assert (text != "foo") is False
    assert hash(text) == hash("foo")
    assert {"foo": 1}.get(text) == 1
    assert text in {"foo"}
    assert len({"foo", text}) == 1
    assert len({text, "foo"}) == 1
    assert text == LangStr("foo")
    assert hash(text) == hash(LangStr("foo"))


def test_tagged_is_distinct_from_str():
    text = LangStr("foo", "eng")
    assert text != "foo"
    assert "foo" != text
    assert (text == "foo") is False
    assert ("foo" == text) is False
    assert {"foo": 1}.get(text) is None
    assert text not in {"foo"}
    assert len({"foo", text}) == 2


def test_tagged_identity_is_content_and_lang():
    eng = LangStr("foo", "eng")
    assert eng == LangStr("foo", "eng")
    assert hash(eng) == hash(LangStr("foo", "eng"))
    assert eng != LangStr("foo", "deu")
    assert eng != LangStr("bar", "eng")
    assert eng != LangStr("foo")
    assert LangStr("foo") != eng
    assert {LangStr("foo", "eng"): 1}.get(eng) == 1
    assert {LangStr("foo", "deu"): 1}.get(eng) is None


def test_set_dedup_is_order_independent():
    eng = LangStr("foo", "eng")
    deu = LangStr("foo", "deu")
    assert len({"foo", eng, deu}) == 3
    assert len({eng, deu, "foo"}) == 3
    assert len({deu, "foo", eng}) == 3
    assert len({LangStr("foo"), "foo", eng}) == 2


def test_non_str_operands():
    class Tagged:
        lang = "eng"

    text = LangStr("foo", "eng")
    assert text != 1
    assert text != None
    assert text != Tagged()
    assert (text == Tagged()) is False
    assert LangStr("foo") != 1
    assert LangStr("foo") != b"foo"
