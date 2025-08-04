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


def test_to_code():
    terr = lookup_territory("Germany")
    assert terr and terr.code == "de"

    terr = lookup_territory("UK")
    assert terr and terr.code == "gb"

    terr = lookup_territory("North Macedonia")
    assert terr and terr.code == "mk"

    assert lookup_territory("Nothing") is None

    terr = lookup_territory("Российская Федерация")
    assert terr and terr.code == "ru"


def test_weird_places():
    terr = lookup_territory("European Union")
    assert terr and terr.code == "eu"

    terr = lookup_territory("Kosovo")
    assert terr and terr.code == "xk"

    terr = lookup_territory("Palestine")
    assert terr and terr.code == "ps"

    terr = lookup_territory("Narnia")
    assert terr is None


def test_non_standard_codes():
    terr = lookup_territory("Taiwan")
    assert terr and terr.code == "tw"

    terr = lookup_territory("Abkhazia")
    assert terr and terr.code == "ge-ab"

    terr = lookup_territory("South Ossetia")
    assert terr and terr.code == "x-so"


def test_fuzzy_matching():
    terr = lookup_territory("Rossiyskaya Federacia", fuzzy=True)
    assert terr and terr.code == "ru"
    terr = lookup_territory("Falklands Islands", fuzzy=True)
    assert terr and terr.code == "fk"
    terr = lookup_territory("TGermany", fuzzy=True)
    assert terr and terr.code == "de"
    terr = lookup_territory("Palestinä", fuzzy=True)
    assert terr and terr.code == "ps"
    terr = lookup_territory("Narnia", fuzzy=True)
    assert terr is None


def test_britain():
    terr = lookup_territory("Scotland")
    assert terr and terr.code == "gb-sct"
    terr = lookup_territory("Wales")
    assert terr and terr.code == "gb-wls"
    terr = lookup_territory("Northern Ireland")
    assert terr and terr.code == "gb-nir"
    terr = lookup_territory("Wales")
    assert terr and terr.code == "gb-wls"
    terr = lookup_territory("United Kingdom of Great Britain and Northern Ireland")
    assert terr and terr.code == "gb"
    misspelled = "United Kigdom fo Great Britain and Northern Ireland"
    terr = lookup_territory(misspelled, fuzzy=True)
    assert terr and terr.code == "gb"
    terr = lookup_territory(misspelled, fuzzy=False)
    assert terr is None
