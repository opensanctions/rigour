from rigour.units import normalize_unit


def test_normalize_unit():
    assert normalize_unit("centimeters") == "cm"
    assert normalize_unit("centimetres") == "cm"
    assert normalize_unit("banana") == "banana"
