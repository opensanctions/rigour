from rigour.names.check import is_name, is_generic_person_name


def test_is_name():
    assert is_name("John")
    assert not is_name("12345")
    assert is_name("A")
    assert not is_name("")
    assert not is_name(" ")
    assert not is_name("---")
    assert is_name("(Mr Bean)")
    assert not is_name("( )")


def test_is_generic_person_name():
    assert is_generic_person_name("abu bakr")
    assert is_generic_person_name("mohammed")
    assert not is_generic_person_name("X Æ A-12")
    assert not is_generic_person_name("The")
    assert not is_generic_person_name("12345")
