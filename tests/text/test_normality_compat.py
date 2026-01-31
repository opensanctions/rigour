"""Test compatibility with normality library's ascii_text function.

These tests are direct copies from normality's test suite to ensure
that rigour.text.ascii_text provides identical behavior.
"""

from rigour.text import ascii_text


def test_empty():
    """Test from normality: test_empty()"""
    assert ascii_text(None) == ""
    assert ascii_text("") == ""


def test_petro():
    """Test from normality: test_petro()"""
    text = "Порошенко Петро Олексійович"
    assert ascii_text(text) == "Porosenko Petro Oleksijovic"


def test_ahmad():
    """Test from normality: test_ahmad()"""
    text = "əhməd"
    assert ascii_text(text) == "ahmad"


def test_azeri():
    """Test from normality: test_azeri()"""
    text = "FUAD ALIYEV ƏHMƏD OĞLU"
    assert ascii_text(text) == "FUAD ALIYEV AHMAD OGLU"


def test_georgian():
    """Test from normality: test_georgian()"""
    text = "ავლაბრის ფონდი"
    assert ascii_text(text) == "avlabris pondi"


def test_german():
    """Test from normality: test_german()"""
    text = "Häschen Spaß"
    assert ascii_text(text) == "Haschen Spass"
