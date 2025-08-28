from rigour.names.check import is_name, is_stopword, is_nullword


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
    assert not is_stopword("The")
    assert is_stopword("The", normalize=True)
    assert is_stopword("and")
    assert not is_stopword("John")
    assert not is_stopword("12345")
    assert not is_stopword("")
    assert not is_stopword(" ")
    assert not is_stopword("---")
    assert not is_stopword("(Mr Bean)")
    assert not is_stopword("( )")


def test_is_nullword():
    assert is_nullword("none")
    assert is_nullword("N/A", normalize=True)
    assert not is_nullword("John")
    assert not is_nullword("12345")
    assert not is_nullword("")
    assert not is_nullword(" ")
    assert not is_nullword("---")
    assert not is_nullword("(Mr Bean)")
    assert not is_nullword("( )")
