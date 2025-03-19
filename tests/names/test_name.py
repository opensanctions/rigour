from rigour.names.name import Name
from rigour.names.tag import NamePartTag, NameTypeTag


def test_name_object():
    name = Name("John Spencer", lang="eng")
    assert name.original == "John Spencer"
    assert str(name) == "John Spencer"
    assert name.form == "john spencer"
    assert name.tag == NameTypeTag.UNK
    assert "Spencer" in repr(name)
    assert "UNK" in repr(name)

    other = Name("John Spencer", lang="fra")
    assert name == other
    assert hash(name) == hash(other)
    assert name != "john spencer"

    assert len(name.parts) == 2
    assert name.parts[0].form == "john"
    assert name.parts[0].ascii == "john"
    assert name.parts[0].tag == NamePartTag.ANY


def test_name_tag_text():
    name = Name("Hans-Peter Mueller")
    name.parts[0].tag == NamePartTag.ANY

    name.tag_text("Hans-Peter", NamePartTag.GIVEN)
    assert name.parts[0].tag == NamePartTag.GIVEN
    assert name.parts[2].tag == NamePartTag.ANY

    name.tag_text("Hans", NamePartTag.PATRONYMIC)
    assert name.parts[0].tag == NamePartTag.GIVEN

    name = Name("Butros Butros Ghali")
    name.tag_text("Butros", NamePartTag.GIVEN, max_matches=1)
    assert name.parts[1].tag == NamePartTag.ANY

    # test repeat
    name.tag_text("Butros", NamePartTag.GIVEN, max_matches=1)
    assert name.parts[1].tag == NamePartTag.ANY

    name.tag_text("Butros", NamePartTag.GIVEN, max_matches=2)
    assert name.parts[1].tag == NamePartTag.GIVEN
