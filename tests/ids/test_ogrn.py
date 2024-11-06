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
    assert OGRN.is_valid("1022600000092")
    assert OGRN.is_valid("1022500001930")
    assert OGRN.is_valid("1022500001061")
    assert OGRN.is_valid("1022500000566")
    assert OGRN.is_valid("1022700000685")
    assert OGRN.is_valid("1022500001325")
    assert OGRN.is_valid("1027100000311")
    assert OGRN.is_valid("1022500000786")
    assert OGRN.is_valid("1024100000121")
    assert OGRN.is_valid("1022400007508")
    assert OGRN.is_valid("1022400000160")
    assert OGRN.is_valid("1022400010005")
    assert OGRN.is_valid("1022300001811")
    assert OGRN.is_valid("1020500003919")
    assert OGRN.is_valid("1022300003703")
    assert OGRN.is_valid("1022300000502")
    assert OGRN.is_valid("1022200531484")
    assert OGRN.is_valid("1022200525819")

    assert not OGRN.is_valid("11677")
    assert not OGRN.is_valid("315774600002662123")
    assert not OGRN.is_valid("1167746691304")
