from rigour.names import tokenize_name


def test_tokenize_name():
    assert tokenize_name("John Doe") == ["John", "Doe"]
    assert tokenize_name("Bond, James Bond") == ["Bond", "James", "Bond"]
    assert tokenize_name("C.I.A.") == ["CIA"]
    assert tokenize_name("Bashar al-Assad") == ["Bashar", "al", "Assad"]
    assert tokenize_name("Bashar al-Assad", token_min_length=3) == ["Bashar", "Assad"]
    assert tokenize_name("بشار الأسد") == ["بشار", "الأسد"]
    # I have no idea if this works for Burmese:
    assert tokenize_name("အောင်ဆန်းစုကြည်") == ["အ", "ငဆန", "စက", "ည"]
