from rigour.addresses.cleaning import clean_address


def test_clean_address():
    assert clean_address("New York, NY") == "New York, NY"
    assert clean_address("New York , NY") == "New York, NY"
    assert clean_address("New York , NY,,") == "New York, NY"
