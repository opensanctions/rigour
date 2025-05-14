from rigour.names.part import NamePart


def test_name_part():
    john = NamePart("john", 0)
    assert john.ascii == "john"
    assert john.maybe_ascii == "john"
    assert john.form == "john"
    assert john.metaphone == "JN"
    assert john.is_modern_alphabet is True
    assert len(john) == 4
    assert hash(john) == hash((0, "john"))
    assert john == NamePart("john", 0)
    assert john != NamePart("john", 1)
    assert repr(john) == "<NamePart('john', 0, 'ANY')>"

    petro = NamePart("Петро́", 0)
    assert petro.ascii == "Petro"
    assert petro.maybe_ascii == "Petro"
    assert petro.metaphone == "PTR"
    assert petro != john
    assert petro != 3

    osama = NamePart("أسامة", 0)
    assert osama.ascii == "asamt"
    assert osama.maybe_ascii == "أسامة"
    assert osama.is_modern_alphabet is False
    assert osama.metaphone is None
