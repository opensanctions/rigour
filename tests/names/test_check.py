from rigour.names.check import is_name, is_stopword


def test_is_name():
    assert is_name("John")
    assert not is_name("12345")
    assert is_name("A")
    assert not is_name("")
    assert not is_name(" ")
    assert not is_name("---")
    assert is_name("(Mr Bean)")
    assert not is_name("( )")


def test_is_stopword():
    assert is_stopword("the")
    assert is_stopword("and")
    assert not is_stopword("John")
    assert not is_stopword("12345")
    assert not is_stopword("")
    assert not is_stopword(" ")
    assert not is_stopword("---")
    assert not is_stopword("(Mr Bean)")
    assert not is_stopword("( )")
