from rigour.addresses.format import format_one_line


def test_format_address():
    addr = {
        "road": "Bahnhofstr.",
        "house_number": "10",
        "postcode": "86150",
        "city": "Augsburg",
        "state": "Bayern",
        "country": "Germany",
    }
    expect = "Bahnhofstr. 10, 86150 Augsburg, Germany"
    assert format_one_line(addr, country="DE") == expect
    addr.pop("country")
    expect = "Bahnhofstr. 10, 86150 Augsburg"
    assert format_one_line(addr, country="DE") == expect
