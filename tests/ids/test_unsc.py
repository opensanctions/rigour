from rigour.ids.unsc import UNSC


def test_unsc():
    # Valid UNSC IDs
    assert UNSC.normalize("QDi.002") == "QDi.002"
    assert UNSC.normalize("QDe.123") == "QDe.123"
    assert UNSC.normalize("CDi.030") == "CDi.030"
    assert UNSC.normalize("CFi.001") == "CFi.001"

    # Valid with whitespace
    assert UNSC.normalize(" QDi.002 ") == "QDi.002"

    # Invalid formats
    assert UNSC.normalize("UNSC banana") is None
    assert UNSC.normalize("ArP.00234") is None
    assert UNSC.normalize("OFAC SDN ID 11177") is None
    assert UNSC.normalize("A-11700/12-2023") is None
    assert UNSC.normalize("OFAC SDN ID 11177ArP.00234") is None

    # Invalid - wrong pattern
    assert UNSC.normalize("QDx.002") is None  # 'x' not 'i' or 'e'
    assert UNSC.normalize("qdi.002") is None  # lowercase
    assert UNSC.normalize("QDi002") is None  # missing dot
    assert UNSC.normalize("QDi.02") is None  # only 2 digits

    # is_valid tests
    assert UNSC.is_valid("QDi.002")
    assert UNSC.is_valid("QDe.123")
    assert UNSC.is_valid("CDi.030")
    assert UNSC.is_valid("ABCe.999")  # 3-letter regime code

    # Invalid
    assert not UNSC.is_valid("ArP.00234")
    assert not UNSC.is_valid("QDi.02")  # too short
    assert not UNSC.is_valid("QDx.002")  # wrong entity type
    assert not UNSC.is_valid("qdi.002")  # lowercase
    assert not UNSC.is_valid("OFAC SDN ID 11177ArP.00234")
