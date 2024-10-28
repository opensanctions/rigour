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

    assert OGRN.is_valid("1027739552642")
    assert not OGRN.is_valid("1027739")

    assert OGRN.is_valid("1137847171846")
    assert OGRN.is_valid("1159102022738")

    assert not OGRN.is_valid("11677")
    assert not OGRN.is_valid("315774600002662123")
    assert not OGRN.is_valid("1167746691304")
    assert not OGRN.is_valid("9167746691301")

if __name__ == "__main__":
    test_ogrn()
    print("All tests passed.")