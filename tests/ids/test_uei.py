from rigour.ids import UEI


def test_uei():
    assert UEI.is_valid("F5L4T8CUYC68")
    assert not UEI.is_valid("F5L4T8CUYC")
    assert not UEI.is_valid("05L4T8CUYC68")
    assert not UEI.is_valid("F5L4T8IUYC68")
    assert UEI.normalize("F5L4T8Cuyc68") == "F5L4T8CUYC68"
    assert UEI.normalize("UEI F5L4T8Cuyc68") == "F5L4T8CUYC68"
    assert UEI.normalize("UEI F5L") is None
    assert UEI.normalize("0F5L4T8Cuyc7") is None
    assert UEI.format("F5L4T8Cuyc68") == "F5L4T8CUYC68"
