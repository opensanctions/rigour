from rigour.langs import iso_639_alpha3, iso_639_alpha2
from rigour.langs import list_to_alpha3
from rigour.langs import PREFERRED_LANG, PREFFERED_LANGS


def test_preferred():
    assert iso_639_alpha3(PREFERRED_LANG) == PREFERRED_LANG
    for lang in PREFFERED_LANGS:
        assert iso_639_alpha3(lang) == lang
        assert iso_639_alpha2(lang) is not None


def test_alpha3():
    assert iso_639_alpha3("") is None
    assert iso_639_alpha3("banana") is None
    assert iso_639_alpha3("gub") == "gub"
    assert iso_639_alpha3("en") == "eng"
    assert iso_639_alpha3("eng") == "eng"
    assert iso_639_alpha3("de") == "deu"
    assert iso_639_alpha3("ger") == "deu"
    assert iso_639_alpha3("yu") is None
    assert iso_639_alpha3("mul") is None
    assert iso_639_alpha3("mul") is None


def test_alpha2():
    assert iso_639_alpha2("") is None
    assert iso_639_alpha2("banana") is None
    assert iso_639_alpha2("gub") is None
    assert iso_639_alpha2("eng") == "en"


def test_list():
    assert "srp" in list_to_alpha3("bs")
    assert "srp" not in list_to_alpha3("bs", synonyms=False)
    assert "deu" in list_to_alpha3(["bs", "de"])
    assert "eng" in list_to_alpha3(["en"])
    assert not len(list_to_alpha3(["xy"]))
    assert not len(list_to_alpha3([""]))
