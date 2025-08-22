from rigour.names.name import Name
from rigour.names.symbol import Symbol
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
    assert name.comparable == "john spencer"

    putin = Name("Владимир Путин", lang="rus")
    assert putin.form == "владимир путин"
    assert putin.norm_form == "владимир путин"
    assert putin.comparable == "vladimir putin"
    assert len(putin.parts) == 2


def test_cjk_name():
    name = Name("维克托·亚历山德罗维奇·卢卡申科", lang="zho")
    assert name.form == "维克托·亚历山德罗维奇·卢卡申科"
    assert name.norm_form == "维克托 亚历山德罗维奇 卢卡申科"
    assert name.comparable == "维克托 亚历山德罗维奇 卢卡申科"
    assert len(name.parts) == 3
    assert name.parts[0].tag == NamePartTag.ANY
    assert name.parts[1].tag == NamePartTag.ANY


def test_name_tag_text():
    name = Name("Hans-Peter Mueller")
    assert name.parts[0].tag == NamePartTag.ANY

    name.tag_text("Hans-Peter", NamePartTag.GIVEN)
    assert name.parts[0].tag == NamePartTag.GIVEN
    assert name.parts[2].tag == NamePartTag.ANY

    name.tag_text("Hans", NamePartTag.PATRONYMIC)
    assert name.parts[0].tag == NamePartTag.GIVEN

    # Contradictory tags should not result in UNSURE:
    name.tag_text("Hans", NamePartTag.FAMILY)
    assert name.parts[0].tag == NamePartTag.UNSURE

    name = Name("Butros Butros Ghali")
    name.tag_text("Butros", NamePartTag.GIVEN, max_matches=1)
    assert name.parts[1].tag == NamePartTag.ANY

    # test repeat
    name.tag_text("Butros", NamePartTag.GIVEN, max_matches=1)
    assert name.parts[1].tag == NamePartTag.ANY

    name.tag_text("Butros", NamePartTag.GIVEN, max_matches=2)
    assert name.parts[1].tag == NamePartTag.GIVEN


def test_name_symbols():
    name = Name("John P Smith-Wesson")
    assert len(name.symbols) == 0
    assert len(name.spans) == 0

    symbol = Symbol(Symbol.Category.INITIAL, "p")
    assert "INITIAL" in repr(symbol)
    assert str(symbol).startswith("[INITIAL")
    name.apply_phrase("p", symbol)
    assert len(name.symbols) == 1
    assert name.symbols == {symbol}
    assert len(name.spans) == 1

    nsymbol = Symbol(Symbol.Category.NAME, "SW")
    assert nsymbol != symbol
    assert nsymbol != "SW"
    name.apply_phrase("smith wesson", nsymbol)
    assert nsymbol in name.symbols
    assert len(name.spans) == 2
    nspan = name.spans[1]
    assert nspan.symbol == nsymbol
    assert len(nspan.parts) == 2
    assert nspan == nspan
    assert "wesson" in repr(nspan)

    bsymbol = Symbol(Symbol.Category.NAME, "BANANA")
    name.apply_phrase("banana", bsymbol)
    assert bsymbol not in name.symbols

    name = Name("J R R Tolkien")
    rsymbol = Symbol(Symbol.Category.INITIAL, "r")
    name.apply_phrase("r", rsymbol)
    assert len(name.symbols) == 1


def test_name_contains_per():
    name1 = Name("John Smith", tag=NameTypeTag.PER)
    assert name1.contains(name1) is False
    name2 = Name("John Smith Jr.", tag=NameTypeTag.PER)
    name3 = Name("John Smith Sr.", tag=NameTypeTag.PER)
    name4 = Name("Jane Smith", tag=NameTypeTag.PER)

    assert name1.contains(name2) is False
    assert name2.contains(name1) is True
    assert name1.contains(name3) is False
    assert name3.contains(name1) is True
    assert name1.contains(name4) is False
    assert name4.contains(name1) is False

    # Test with same names but different tags
    name5 = Name("John Randolph Smith", tag=NameTypeTag.PER)
    assert name1.contains(name5) is False
    assert name5.contains(name1) is True

    symbol = Symbol(Symbol.Category.INITIAL, "r")
    name5.apply_phrase("randolph", symbol)

    name6 = Name("John R. Smith", tag=NameTypeTag.PER)
    name6.apply_phrase("r", symbol)
    assert name5.contains(name6) is True
    assert name6.contains(name5) is False


def test_name_contains_org():
    comp1 = Name("Banana Republic Inc.", tag=NameTypeTag.ORG)
    comp2 = Name("Banana Republic", tag=NameTypeTag.ORG)
    assert comp1.contains(comp2) is True
    assert comp2.contains(comp1) is False

    # Should this match?
    comp1 = Name("Banana Republics Inc.", tag=NameTypeTag.ORG)
    comp2 = Name("Banana Republic", tag=NameTypeTag.ORG)
    assert comp1.contains(comp2) is True
    assert comp2.contains(comp1) is False


def test_name_contains_order():
    name1 = Name("John Smith", tag=NameTypeTag.PER)
    name2 = Name("Smith, John", tag=NameTypeTag.PER)
    assert name1.contains(name2) is True
    assert name2.contains(name1) is True

    name1 = Name("John Smith", tag=NameTypeTag.PER)
    name2 = Name("Smith, John Richard", tag=NameTypeTag.PER)
    assert name1.contains(name2) is False
    assert name2.contains(name1) is True

    name1 = Name("Republic Banana Inc", tag=NameTypeTag.ORG)
    name2 = Name("Banana Republic Inc", tag=NameTypeTag.ORG)
    assert name1.contains(name2) is False
    assert name2.contains(name1) is False


def test_name_contains_unk():
    # Unknwon type never matches
    name1 = Name("John Smith", tag=NameTypeTag.UNK)
    name2 = Name("John Smith Jr.", tag=NameTypeTag.UNK)
    assert name1.contains(name2) is False
