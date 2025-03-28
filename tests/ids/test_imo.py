from rigour.ids import IMO


def test_ship_imo():
    assert IMO.normalize("IMO 9126819") == "IMO9126819"
    assert IMO.normalize("IMO9126819") == "IMO9126819"
    assert IMO.normalize("9126819") == "IMO9126819"
    assert IMO.normalize("91268191") is None
    assert IMO.normalize("IMO 912681") is None
    assert IMO.is_valid("IMO 9126819")
    assert IMO.is_valid("9126819")
    assert not IMO.is_valid("IMO 9126")
    assert not IMO.is_valid("9126")
    assert not IMO.is_valid("")
    assert IMO.format("9126819") == "IMO9126819"
    assert IMO.format("IMO9126819") == "IMO9126819"
    assert IMO.normalize("IMO number: 9126819") == "IMO9126819"


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
