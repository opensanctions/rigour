import pytest

from rigour.ids import get_identifier_format, get_identifier_formats
from rigour.ids import get_identifier_format_names
from rigour.ids.common import IdentifierType
from rigour.ids.strict import StrictIdentifier

def test_get_identifier_format():
    assert issubclass(get_identifier_format("wikidata"), IdentifierType)
    assert issubclass(get_identifier_format("qid"), IdentifierType)
    assert get_identifier_format("wikidata") == get_identifier_format("qid")
    assert pytest.raises(KeyError, get_identifier_format, "foo")
    assert get_identifier_format("generic") == IdentifierType
    assert get_identifier_format("null") == IdentifierType
    assert get_identifier_format("strict") == StrictIdentifier

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
    assert IdentifierType.is_valid("foo") is True
    assert IdentifierType.is_valid("") is False
    assert IdentifierType.normalize("foo") == 'foo'
    assert IdentifierType.normalize("foo ") == 'foo'

def test_strict_identifier():
    assert StrictIdentifier.is_valid("foo") is True
    assert StrictIdentifier.is_valid("") is False
    assert StrictIdentifier.normalize("foo") == 'FOO'
    assert StrictIdentifier.normalize("foo ") == 'FOO'
    assert StrictIdentifier.normalize("F-OO") == 'FOO'
    assert StrictIdentifier.normalize("FäOO") == 'FAOO'
    assert StrictIdentifier.normalize("") is None