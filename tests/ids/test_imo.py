from rigour.ids import IMO


def test_ship_imo():
    assert IMO.normalize("IMO 9126819") == "IMO9126819"
    assert IMO.normalize("IMO9126819") == "IMO9126819"
    assert IMO.normalize("9126819") == "IMO9126819"
    assert IMO.normalize("91268191") is None
    assert IMO.is_valid("IMO 9126819")
    assert IMO.is_valid("9126819")
    assert not IMO.is_valid("IMO 9126")
    assert not IMO.is_valid("9126")
    assert not IMO.is_valid("")
    assert IMO.format("9126819") == "IMO9126819"
    assert IMO.format("IMO9126819") == "IMO9126819"
    assert IMO.normalize("IMO number: 9126819") == "IMO9126819"


def test_imo_leading_zero_stripped():
    # Sources sometimes strip leading zeros — pad back to 7 before checksum.
    assert IMO.normalize("912681") == "IMO0912681"
    assert IMO.normalize("IMO 912681") == "IMO0912681"
    assert IMO.is_valid("912681")
    # Two stripped zeros (a five-digit run) are still recoverable.
    assert IMO.normalize("12343") == "IMO0012343"
    # Padding should not turn an unrelated short number into a valid IMO.
    assert not IMO.is_valid("9126")
    assert IMO.normalize("9126") is None


def test_org_imo():
    assert IMO.normalize("IMO 6459297") == "IMO6459297"
    assert IMO.is_valid("IMO 6459297")
    assert not IMO.is_valid("IMO 64592971")
    assert IMO.format("IMO6459297") == "IMO6459297"
    assert IMO.is_valid("IMO 2041999")
    assert IMO.is_valid("IMO 1865817")
    assert IMO.normalize("IMO 1865817") == "IMO1865817"

    assert IMO.normalize("IMO 6459298") is None
    assert not IMO.is_valid("IMO 6459298")


def test_imo_extraction_selection():
    # A stray short number must not shadow the real IMO (issue #249).
    assert IMO.normalize("Flag 12, IMO 9289518") == "IMO9289518"
    # Fall-through: the first 7-digit run has a bad checksum, the second wins.
    assert IMO.normalize("9289519 / 9126819") == "IMO9126819"
    # A prefixed run beats an unprefixed one of the same length.
    assert IMO.normalize("1234567 IMO 9126819") == "IMO9126819"
    # 8+-digit runs (e.g. MMSI) are never candidates.
    assert IMO.normalize("MMSI 373817000, 912681") == "IMO0912681"
    # An invalid IMO stays invalid however it is spelled.
    assert IMO.normalize("IMO 9289519") is None
    assert IMO.normalize("9289519") is None


def test_imo_placeholder_garbage():
    # Zero-ish placeholders must not converge on a phantom "IMO0000000".
    assert not IMO.is_valid("0")
    assert not IMO.is_valid("000")
    assert not IMO.is_valid("0000000")
    assert IMO.normalize("IMO 0000000") is None
    assert IMO.normalize("12") is None


def test_imo_schemes():
    # 9126819 is a ship number, 6459297 a company number.
    assert IMO.is_valid_vessel("IMO 9126819")
    assert not IMO.is_valid_company("IMO 9126819")
    assert IMO.is_valid_company("IMO 6459297")
    assert not IMO.is_valid_vessel("IMO 6459297")
    # The scheme checks run the same extraction pipeline, padding included.
    assert IMO.is_valid_company("344771")
    assert not IMO.is_valid_vessel("344771")
    assert not IMO.is_valid_vessel("")
    assert not IMO.is_valid_company("0000000")
