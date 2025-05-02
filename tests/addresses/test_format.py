from rigour.addresses.format import format_address, format_address_line


def test_format_address():
    addr = {
        "road": "Bahnhofstr.",
        "house_number": "10",
        "postcode": "86150",
        "city": "Augsburg",
        "state": "Bayern",
        "country": "Germany",
    }
    expect = "Bahnhofstr. 10\n86150 Augsburg\nGermany"
    assert format_address(addr, country="DE") == expect

    data = {
        "road": "Broad St",
        "house_number": "160",
        "city": "Birmingham",
        "postcode": "B15 1DT",
    }
    expect = "160 Broad St\nBirmingham\nB15 1DT"
    assert format_address(data, country="GB") == expect

    data = {
        "road": "Pall Mall",
        "house": "Marlborough House",
        "city": "London",
        "postcode": "SW1Y 5HX",
    }
    expect = "Marlborough House\nPall Mall\nLondon\nSW1Y 5HX"
    assert format_address(data, country="GB") == expect

    data = {
        "suburb": "Beverley",
        "road": "Beverley Rd",
        "city": "Kingston",
        "state": "Ontario",
    }
    expect = "Beverley\nKingston, Ontario"
    assert format_address(data, country="CA") == expect

    data = {
        "suburb": "Beverley",
        "road": "Beverley Rd",
        "house_number": "10",
        "city": "Kingston",
        "state": "Ontario",
    }
    expect = "10 Beverley Rd\nKingston, Ontario"
    assert format_address(data, country="CA") == expect

def test_format_address_line():
    addr = {
        "road": "Bahnhofstr.",
        "house_number": "10",
        "postcode": "86150",
        "city": "Augsburg",
        "state": "Bayern",
        "country": "Germany",
    }
    expect = "Bahnhofstr. 10, 86150 Augsburg, Germany"
    assert format_address_line(addr, country="DE") == expect
    addr.pop("country")
    expect = "Bahnhofstr. 10, 86150 Augsburg"
    assert format_address_line(addr, country="DE") == expect

    addr = {"road": "Sesame Street", "house_number": "16", "state": "Dubai"}
    expect = "16 Sesame Street, Dubai"
    assert format_address_line(addr, country="AE-DU") == expect

    addr = {"road": "Sesame Street", "country": "Fantastan"}
    expect = "Sesame Street, Fantastan"
    assert format_address_line(addr, country="XX") == expect

    addr = {"road": "Sesame Street", "house_number": None, "country": "Fantastan"}
    expect = "Sesame Street, Fantastan"
    assert format_address_line(addr, country="XX") == expect

    addr = {"road": "Sesame Street", "house_number": "", "country": "Fantastan"}
    expect = "Sesame Street, Fantastan"
    assert format_address_line(addr, country="XX") == expect

    addr = {"road": "Main Street", "house_number": "16", "city": "Guerntown"}
    expect = "16 Main Street, Guerntown, Guernsey, Channel Islands"
    assert format_address_line(addr, country="GG") == expect
