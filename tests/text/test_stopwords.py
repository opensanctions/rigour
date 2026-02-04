from rigour.text.stopwords import is_stopword, is_nullword, is_nullplace


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


def test_is_nullplace():
    assert is_nullplace("stateless")
    assert is_nullplace("overseas")
    assert is_nullplace("Overseas", normalize=True)
    assert is_nullplace("west indies")
    assert not is_nullplace("France")
    assert not is_nullplace("United States")
    assert not is_nullplace("")
