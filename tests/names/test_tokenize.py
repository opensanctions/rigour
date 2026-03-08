from rigour.names import tokenize_name, normalize_name


def test_tokenize_name():
    assert tokenize_name("John Doe") == ["John", "Doe"]
    assert tokenize_name("Bond, James Bond") == ["Bond", "James", "Bond"]
    assert tokenize_name("C.I.A.") == ["CIA"]
    assert tokenize_name("Bashar al-Assad") == ["Bashar", "al", "Assad"]
    assert tokenize_name("Bashar al-Assad", token_min_length=3) == ["Bashar", "Assad"]
    assert tokenize_name("بشار الأسد") == ["بشار", "الأسد"]
    assert tokenize_name("维克托·亚历山德罗维奇·卢卡申科") == [
        "维克托",
        "亚历山德罗维奇",
        "卢卡申科",
    ]
    # I have no idea if this works for Burmese:
    assert tokenize_name("အောင်ဆန်းစုကြည်") == ["အ", "ငဆန", "စက", "ည"]


def test_tokenize_skip_characters():
    assert tokenize_name("O\u0027Brien", token_min_length=1) == ["OBrien"]  # ASCII apostrophe
    assert tokenize_name("O\u2019Brien", token_min_length=1) == ["OBrien"]  # right single quote
    assert tokenize_name("O\u2018Brien", token_min_length=1) == ["OBrien"]  # left single quote
    assert tokenize_name("O\u02BCBrien", token_min_length=1) == ["OBrien"]  # modifier apostrophe
    assert tokenize_name("U.S.A.", token_min_length=1) == ["USA"]
    assert tokenize_name("...", token_min_length=1) == []


def test_tokenize_edge_cases():
    assert tokenize_name("", token_min_length=1) == []
    assert tokenize_name("---", token_min_length=1) == []
    assert tokenize_name("foo  bar", token_min_length=1) == ["foo", "bar"]
    assert tokenize_name(" foo ", token_min_length=1) == ["foo"]
    assert tokenize_name("foo", token_min_length=4) == []


def test_tokenize_unicode_categories():
    assert tokenize_name("foo\x00bar", token_min_length=1) == ["foo", "bar"]  # Cc → WS
    assert tokenize_name("foo\u200bbar", token_min_length=1) == ["foobar"]  # Cf → deleted
    assert tokenize_name("a+b", token_min_length=1) == ["a", "b"]  # Sm → WS
    assert tokenize_name("$100", token_min_length=1) == ["100"]  # Sc → deleted
    assert tokenize_name("n\u0308", token_min_length=1) == ["n"]  # Mn → deleted


def test_normalize_name():
    assert normalize_name(None) is None
    assert normalize_name("") is None
    assert normalize_name("---") is None
    assert normalize_name("John Doe") == "john doe"
