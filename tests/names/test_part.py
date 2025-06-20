from rigour.names.part import NamePart
from rigour.names.tag import NamePartTag


def test_name_part():
    john = NamePart("john", 0)
    assert john.ascii == "john"
    assert john.comparable == "john"
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
    assert petro.comparable == "Petro"
    assert petro.metaphone == "PTR"
    assert petro != john
    assert petro != 3

    osama = NamePart("أسامة", 0)
    assert osama.ascii == "asamt"
    assert osama.comparable == "أسامة"
    assert osama.is_modern_alphabet is False
    assert osama.metaphone is None


def test_name_part_empty():
    # Should never exist
    empty = NamePart("", 0)
    assert empty.ascii is None
    assert empty.comparable == ""
    assert empty.metaphone is None
    assert empty.is_modern_alphabet is True


def test_name_part_tags():
    john = NamePart("john", 0)
    steven = NamePart("steven", 0, NamePartTag.GIVEN)
    assert steven.can_match(john)
    stevens = NamePart("stevens", 0, NamePartTag.FAMILY)
    assert not steven.can_match(stevens)
    assert not stevens.can_match(steven)

    sorted = NamePart.tag_sort([stevens, steven, john])
    assert sorted == [steven, john, stevens]

    smith = NamePart("smith", 0)
    assert NamePart.tag_sort([smith, john]) == [smith, john]
    assert NamePart.tag_sort([john, smith]) == [john, smith]
