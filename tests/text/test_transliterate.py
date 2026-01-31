"""Tests for text transliteration functions.

These tests are adapted from the normality library to ensure compatibility.
"""

from rigour.text import ascii_text


def test_empty():
    """Test handling of None and empty strings."""
    assert ascii_text(None) == ""
    assert ascii_text("") == ""


def test_petro():
    """Test Ukrainian transliteration (Poroshenko)."""
    text = "Порошенко Петро Олексійович"
    assert ascii_text(text) == "Porosenko Petro Oleksijovic"


def test_ahmad():
    """Test schwa character transliteration."""
    text = "əhməd"
    assert ascii_text(text) == "ahmad"


def test_azeri():
    """Test Azerbaijani transliteration."""
    text = "FUAD ALIYEV ƏHMƏD OĞLU"
    assert ascii_text(text) == "FUAD ALIYEV AHMAD OGLU"


def test_georgian():
    """Test Georgian script transliteration."""
    text = "ავლაბრის ფონდი"
    assert ascii_text(text) == "avlabris pondi"


def test_german():
    """Test German umlauts and eszett."""
    text = "Häschen Spaß"
    assert ascii_text(text) == "Haschen Spass"


def test_already_ascii():
    """Test that ASCII text is returned unchanged."""
    assert ascii_text("hello world") == "hello world"
    assert ascii_text("123") == "123"
    assert ascii_text("test") == "test"


def test_cyrillic():
    """Test Cyrillic transliteration."""
    assert ascii_text("Москва") == "Moskva"
    assert ascii_text("АМУРСКАЯ") == "AMURSKAA"
    assert ascii_text("Д.127") == "D.127"


def test_accents():
    """Test accent removal."""
    assert ascii_text("Café") == "Cafe"
    assert ascii_text("naïve") == "naive"
    assert ascii_text("résumé") == "resume"


def test_mixed_scripts():
    """Test text with mixed scripts."""
    text = "Test 123 Café Москва"
    result = ascii_text(text)
    assert result.isascii()
    assert "Test" in result
    assert "123" in result
    assert "Cafe" in result
    assert "Moskva" in result


def test_arabic():
    """Test Arabic transliteration."""
    text = "مرحبا"
    result = ascii_text(text)
    assert result.isascii()
    # ICU should produce some Latin output
    assert len(result) > 0


def test_chinese():
    """Test Chinese transliteration."""
    text = "你好"
    result = ascii_text(text)
    assert result.isascii()
    # ICU should produce some Latin output
    assert len(result) > 0


def test_result_always_ascii():
    """Property test: result should always be ASCII."""
    test_cases = [
        "Café",
        "Москва",
        "مرحبا",
        "Здравствуйте",
        "你好",
        "ავლაბრის",
        "Häschen",
        "Порошенко",
        "əhməd",
    ]

    for text in test_cases:
        result = ascii_text(text)
        assert result.isascii(), f"ascii_text({text!r}) produced non-ASCII: {result!r}"


def test_preserves_spaces():
    """Test that whitespace is preserved."""
    assert ascii_text("hello world") == "hello world"
    assert ascii_text("  spaces  ") == "  spaces  "


def test_preserves_numbers():
    """Test that numbers are preserved."""
    assert ascii_text("123") == "123"
    assert ascii_text("test 456 test") == "test 456 test"


def test_removes_symbols():
    """Test that certain symbols are removed."""
    # ICU's ASCII_SCRIPT includes [:Symbol:] Remove
    # So symbols should be removed or converted
    result = ascii_text("test★test")
    assert result.isascii()


def test_case_preservation():
    """Test that case is preserved."""
    assert ascii_text("UPPERCASE") == "UPPERCASE"
    assert ascii_text("lowercase") == "lowercase"
    assert ascii_text("MixedCase") == "MixedCase"
