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
    assert hash(text) == hash("Hello")
    assert text != LangStr("Hello", lang="deu")

    with pytest.raises(ValueError):
        LangStr("Hello", lang="invalid")


def test_langstr_hash_eq_contract():
    """LangStr must satisfy a == b => hash(a) == hash(b) with plain str (#255)."""
    a = LangStr("foo", "eng")
    assert a == "foo"
    assert hash(a) == hash("foo")
    assert "foo" == a
    assert hash("foo") == hash(a)


def test_langstr_str_keyed_dict():
    """LangStr lookups in str-keyed dicts must work after the hash fix (#255)."""
    a = LangStr("foo", "eng")
    d = {"foo": 1}
    assert d.get(a) == 1
    assert a in d


def test_langstr_str_keyed_set():
    """LangStr instances equal to a plain str must deduplicate in sets (#255)."""
    a = LangStr("foo", "eng")
    s = {"foo", a}
    assert len(s) == 1
    assert "foo" in s


def test_langstr_lang_differing():
    """Two LangStrs with same text but different lang share a hash bucket.

    They are NOT equal (lang differs), but they must hash to the same value
    since both compare equal to the same plain str — the hash/eq contract
    requires hash(a) == hash(b) whenever a == c and b == c for a common c.
    """
    a = LangStr("foo", "eng")
    b = LangStr("foo", "deu")
    assert a != b
    assert hash(a) == hash(b)


def test_langstr_none_lang():
    """LangStr with None lang still satisfies the hash/eq contract."""
    a = LangStr("foo", None)
    assert a == "foo"
    assert hash(a) == hash("foo")
