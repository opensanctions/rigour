from rigour.text.numbers import string_number


def test_ascii_ints_and_floats():
    assert string_number("123") == 123.0
    assert string_number("0") == 0.0
    assert string_number("42") == 42.0
    assert string_number("-42") == -42.0
    assert string_number("2.5") == 2.5
    assert string_number("1e3") == 1000.0


def test_rejects_empty_and_non_numeric():
    assert string_number("") is None
    assert string_number("abc") is None
    assert string_number("!") is None
    assert string_number("1a") is None


def test_non_ascii_decimal_digits():
    # Arabic-Indic ٤٥٦ = 456
    assert string_number("\u0664\u0665\u0666") == 456.0
    # Extended Arabic-Indic ۱۲۳ = 123
    assert string_number("\u06f1\u06f2\u06f3") == 123.0
    # Devanagari १२३ = 123
    assert string_number("\u0967\u0968\u0969") == 123.0
    # Fullwidth １２３ = 123
    assert string_number("\uff11\uff12\uff13") == 123.0


def test_roman_numerals():
    # Single-char in the dedicated Roman block.
    assert string_number("\u216b") == 12.0   # Ⅻ
    assert string_number("\u216f") == 1000.0 # Ⅿ
    assert string_number("\u217b") == 12.0   # ⅻ (lowercase)

    # Multi-char Roman runs are rejected. Python's pre-port implementation
    # returned 105100 for "ⅯⅮⅭ" (1000*10 + 500 = 10500, *10 + 100 = 105100);
    # the Rust port refuses to pretend it can parse Roman notation.
    assert string_number("\u216f\u216e\u216d") is None  # ⅯⅮⅭ


def test_latin_letters_not_roman():
    # ASCII Latin M/D/C/L/X/V/I have no Unicode Numeric_Value — only the
    # dedicated U+2160+ glyphs do. Latin text is never interpreted as
    # Roman.
    assert string_number("M") is None
    assert string_number("MCMLXXXIV") is None
    assert string_number("XII") is None


def test_vulgar_fractions():
    assert string_number("\u00bd") == 0.5    # ½
    assert string_number("\u00bc") == 0.25   # ¼
    assert string_number("\u00be") == 0.75   # ¾


def test_digit_plus_fraction_rejected():
    # Python's pre-port implementation returned 30.5 for "3½" (3*10 + 0.5)
    # because the per-char multiply-by-ten loop didn't care about value
    # magnitude. The port rejects mixed 0..10 digits with fractional /
    # large values.
    assert string_number("3\u00bd") is None  # 3½
    assert string_number("1\u00bd") is None


def test_cjk_single_char():
    assert string_number("萬") == 10000.0
    assert string_number("億") == 100000000.0
    assert string_number("十") == 10.0


def test_cjk_per_digit_run():
    # 一二三 = 1, 2, 3 — all 0..10 integers, so the accumulation path
    # fires: ((1)*10+2)*10+3 = 123.
    assert string_number("一二三") == 123.0
    assert string_number("九九九") == 999.0


def test_cjk_mixed_rejected():
    # "萬五" mixes a large value (10000) with a small digit — reject.
    assert string_number("萬五") is None
