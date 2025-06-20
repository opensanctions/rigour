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

    bsymbol = Symbol(Symbol.Category.NAME, "BANANA")
    name.apply_phrase("banana", bsymbol)
    assert bsymbol not in name.symbols

    name = Name("J R R Tolkien")
    rsymbol = Symbol(Symbol.Category.INITIAL, "r")
    name.apply_phrase("r", rsymbol)
    assert len(name.symbols) == 1
    map = name.symbol_map()
    assert len(map) == 1
    assert len(map[rsymbol]) == 2
