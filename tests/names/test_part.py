from rigour.names.part import NamePart
from rigour.names.tag import NamePartTag


def test_name_part():
    john = NamePart("john", 0)
    assert john.ascii == "john"
    assert john.comparable == "john"
    assert john.form == "john"
    assert john.metaphone == "JN"
    assert john.latinize is True
    assert john.numeric is False
    assert len(john) == 4
    assert hash(john) == hash((0, "john"))
    assert john == NamePart("john", 0)
    assert john != NamePart("john", 1)
    assert repr(john) == "<NamePart('john', 0, 'UNSET')>"

    petro = NamePart("Петро́", 0)
    assert petro.ascii == "Petro"
    assert petro.comparable == "Petro"
    assert petro.metaphone == "PTR"
    assert petro != john
    assert petro != 3

    osama = NamePart("أسامة", 0)
    assert osama.ascii == "asamt"
    assert osama.comparable == "أسامة"
    assert osama.latinize is False
    assert osama.metaphone is None

    numeric = NamePart("1234", 0)
    assert numeric.ascii == "1234"
    assert numeric.comparable == "1234"
    assert numeric.integer == 1234
    assert numeric.metaphone is None
    assert numeric.latinize is True
    assert numeric.numeric is True


def test_name_part_empty():
    # Should never exist
    empty = NamePart("", 0)
    assert empty.ascii is None
    assert empty.comparable == ""
    assert empty.metaphone is None
    assert empty.latinize is True
    assert empty.numeric is False


def test_name_part_tags():
    john = NamePart("john", 0)
    steven = NamePart("steven", 0, NamePartTag.GIVEN)
    assert steven.can_match(john)
    stevens = NamePart("stevens", 0, NamePartTag.FAMILY)
    assert not steven.can_match(stevens)
    assert not stevens.can_match(steven)

    anyst = NamePart("steven", 0, NamePartTag.UNSET)
    assert anyst.can_match(steven)
    assert anyst.can_match(stevens)


def test_name_part_numeric():
    name = NamePart("Ⅻ", 1)
    assert name.numeric is True
    assert name.ascii == "12"
    assert name.comparable == "12"
    assert name.integer == 12
    assert name.metaphone is None


def test_name_part_sort():
    john = NamePart("john", 0)
    steven = NamePart("steven", 0, NamePartTag.GIVEN)
    stevens = NamePart("stevens", 0, NamePartTag.FAMILY)
    sorted = NamePart.tag_sort([stevens, steven, john])
    assert sorted == [steven, john, stevens]

    smith = NamePart("smith", 0)
    assert NamePart.tag_sort([smith, john]) == [smith, john]
    assert NamePart.tag_sort([john, smith]) == [john, smith]


def name_part_sort_company():
    parts = [
        NamePart("llc", 0, NamePartTag.LEGAL),
        NamePart("orion", 1, NamePartTag.UNSET),
    ]
    sorted_parts = NamePart.tag_sort(parts)
    assert len(sorted_parts) == 2
    assert sorted_parts[0].form == "orion"
    assert sorted_parts[1].form == "llc"
    parts = [
        NamePart("orion", 0, NamePartTag.UNSET),
        NamePart("llc", 1, NamePartTag.LEGAL),
    ]
    sorted_parts = NamePart.tag_sort(parts)
    assert len(sorted_parts) == 2
    assert sorted_parts[0].form == "orion"
    assert sorted_parts[1].form == "llc"


def test_name_part_sort_stable():
    parts = [
        NamePart("a", 0, NamePartTag.UNSET),
        NamePart("c", 1, NamePartTag.UNSET),
        NamePart("x", 1, NamePartTag.UNSET),
    ]
    sorted_parts = NamePart.tag_sort(parts)
    assert len(sorted_parts) == 3
    assert sorted_parts[0].form == "a"
    assert sorted_parts[1].form == "c"
    assert sorted_parts[2].form == "x"
    parts = [
        NamePart("x", 0, NamePartTag.UNSET),
        NamePart("c", 1, NamePartTag.UNSET),
        NamePart("a", 1, NamePartTag.UNSET),
    ]
    sorted_parts = NamePart.tag_sort(parts)
    assert len(sorted_parts) == 3
    assert sorted_parts[0].form == "x"
    assert sorted_parts[1].form == "c"
    assert sorted_parts[2].form == "a"
