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
