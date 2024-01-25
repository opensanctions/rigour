from rigour.langs import iso_639_alpha3, iso_639_alpha2
from rigour.langs import list_to_alpha3

def test_alpha3():
    assert iso_639_alpha3("") is None
    assert iso_639_alpha3("banana") is None
    assert iso_639_alpha3("gub") == "gub"
    assert iso_639_alpha3("en") == "eng"
    assert iso_639_alpha3("eng") == "eng"
    assert iso_639_alpha3("yu") is None

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
