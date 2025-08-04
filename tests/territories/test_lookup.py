from rigour.territories import lookup_by_identifier
from rigour.territories import lookup_territory


def test_lookup_by_identifier():
    """Test the lookup_by_identifier function."""
    territory = lookup_by_identifier("US")
    assert territory is not None
    assert territory.code == "us"

    # Test with a QID
    territory = lookup_territory("Q30")  # QID for the United States
    assert territory is not None
    assert territory.code == "us"

    territory = lookup_by_identifier("XYZ")
    assert territory is None


def test_lookup_territory():
    """Test the lookup_territory function."""
    territory = lookup_territory("United States")
    assert territory is not None
    assert territory.code == "us"

    territory = lookup_territory("United States of America")
    assert territory is not None
    assert territory.code == "us"

    territory = lookup_territory("USA")
    assert territory is not None
    assert territory.code == "us"

    territory = lookup_territory("Nonexistent Territory")
    assert territory is None

    assert False
