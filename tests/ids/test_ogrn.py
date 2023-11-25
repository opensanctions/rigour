from rigour.ids.ogrn import OGRN


def test_ogrn():
    assert OGRN.is_valid("1027739552642")
    assert not OGRN.is_valid("1027739552")
    assert not OGRN.is_valid("")
    assert OGRN.normalize("1027739552642") == "1027739552642"
    assert OGRN.normalize("OGRN 1027739552642") == "1027739552642"
    assert OGRN.normalize("102773955") is None
    assert OGRN.normalize("10277395587984375943") is None
    assert OGRN.format("1027739552642") == "1027739552642"
