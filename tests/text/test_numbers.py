from rigour.text.numbers import string_number


def test_string_numbers():
    assert string_number("123") == 123.0
    assert string_number("٤٥٦") == 456.0  # Arabic-Indic digits
    assert string_number("Ⅻ") == 12.0  # Roman numeral for 12
    assert string_number("一二三") == 123.0  # Chinese numerals
    assert string_number("abc") is None  # Non-numeric string
    assert string_number("!") is None  # Non-numeric string
    assert string_number("1a") is None  # Non-numeric string
    assert string_number("") is None  # Empty string
    assert string_number("１２３") == 123.0  # Fullwidth digits
    assert string_number("萬") == 10000.0  # Chinese character for 10,000
