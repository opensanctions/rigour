from rigour.addresses import normalize_address


def test_normalize_address():
    address = "Bahnhofstr. 10, 86150 Augsburg, Germany"
    assert normalize_address(address, sep="") == "bahnhofstr1086150augsburggermany"

    address = "160 Broad St, Birmingham B15 1DT"
    assert normalize_address(address, sep="") == "160broadstbirminghamb151dt"

    address = "160 Broad` St, Birmingham B15 1DT"
    assert normalize_address(address, sep="") == "160broadstbirminghamb151dt"

    address = "160 Broad Street, Birmingham B15 1DT"
    assert normalize_address(address, sep="") == "160broadstbirminghamb151dt"

    address = "Marlborough House, Pall Mall, London SW1Y 5HX"
    assert normalize_address(address, sep="") == "marlboroughhousepallmalllondonsw1y5hx"

    assert normalize_address("hey") is None
    assert normalize_address("") is None
    assert normalize_address("h e d", sep="") is None
    assert normalize_address("h e d", sep=" ") is not None

    assert (
        normalize_address("Д.127, АМУРСКАЯ, АМУРСКАЯ, 675000", sep="")
        == "д127амурскаяамурская675000"
    )
    assert (
        normalize_address("Д.127, АМУРСКАЯ, АМУРСКАЯ, 675000", sep="", latinize=True)
        == "d127amurskaaamurskaa675000"
    )
