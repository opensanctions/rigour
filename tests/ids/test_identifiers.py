import pytest

from rigour.ids import get_identifier_format, get_identifier_formats
from rigour.ids import get_identifier_format_names
from rigour.ids.common import IdentifierFormat
from rigour.ids.strict import StrictFormat

def test_get_identifier_format():
    assert issubclass(get_identifier_format("wikidata"), IdentifierFormat)
    assert issubclass(get_identifier_format("qid"), IdentifierFormat)
    assert get_identifier_format("wikidata") == get_identifier_format("qid")
    assert pytest.raises(KeyError, get_identifier_format, "foo")
    assert get_identifier_format("generic") == IdentifierFormat
    assert get_identifier_format("null") == IdentifierFormat
    assert get_identifier_format("strict") == StrictFormat

def test_get_identifier_format_names():
    assert "wikidata" in get_identifier_format_names()
    assert "qid" in get_identifier_format_names()
    assert "foo" not in get_identifier_format_names()
    assert "generic" in get_identifier_format_names()
    assert "null" in get_identifier_format_names()
    assert "strict" in get_identifier_format_names()

def test_get_identifier_formats():
    formats = get_identifier_formats()
    assert len(formats) > 5
    for fmt in formats:
        assert len(fmt['description']) > 5, fmt
        assert len(fmt['names']) > 0, fmt
        assert len(fmt['title']) > 1, fmt

def test_generic_identifier():
    assert IdentifierFormat.is_valid("foo") is True
    assert IdentifierFormat.is_valid("") is False
    assert IdentifierFormat.normalize("foo") == 'foo'
    assert IdentifierFormat.normalize("foo ") == 'foo'

def test_strict_identifier():
    assert StrictFormat.is_valid("foo") is True
    assert StrictFormat.is_valid("") is False
    assert StrictFormat.normalize("foo") == 'FOO'
    assert StrictFormat.normalize("foo ") == 'FOO'
    assert StrictFormat.normalize("F-OO") == 'FOO'
    assert StrictFormat.normalize("FäOO") == 'FAOO'
    assert StrictFormat.normalize("") is None
