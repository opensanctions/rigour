from rigour.ids.ogrn import OGRN


def test_ogrn():
    # === Valid Cases ===
    # 13-digit valid OGRN (standard)
    assert OGRN.is_valid("1027739552642")
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
    assert OGRN.is_valid("385768585948949")
    assert not OGRN.is_valid("385768585948948")
    assert not OGRN.is_valid("38576858")
    assert not OGRN.is_valid("0022200525819")
    assert not OGRN.is_valid("1029790525819")

    # === Invalid Cases ===
    # Too short
    assert not OGRN.is_valid("1027739")  # only 7 digits

    # Too long
    assert not OGRN.is_valid("315774600002662123")  # 18 digits

    # Contains invalid characters or wrong format
    assert not OGRN.is_valid("OGRN 1027739552642")  # Contains "OGRN"
    assert not OGRN.is_valid("11677")  # Very short example

    # Edge case: Almost valid, but with an extra digit
    assert not OGRN.is_valid("10277395526422")  # 14 digits instead of 13 or 15

    # === Normalization Tests ===
    # Correct normalization of standard format
    assert OGRN.normalize("1027739552642") == "1027739552642"
    assert OGRN.normalize("1027739552643") is None

    # Normalization removes extra text
    assert OGRN.normalize("OGRN 1027739552642") == "1027739552642"

    # Normalization fails for incorrect formats
    assert OGRN.normalize("102773955") is None  # too short
    assert OGRN.normalize("10277395587984375943") is None  # too long

    # === Formatting Tests ===
    # Check if formatting returns as expected
    assert OGRN.format("1027739552642") == "1027739552642"
