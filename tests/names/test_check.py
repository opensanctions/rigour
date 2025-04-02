from rigour.names.check import is_name


def test_is_name():
    assert is_name("John")
    assert not is_name("12345")
    assert is_name("A")
    assert not is_name("")
    assert not is_name(" ")
    assert not is_name("---")
    assert is_name("(Mr Bean)")
    assert not is_name("( )")
