from rigour.ids.npi import NPI


def test_npi():
    assert NPI.normalize("1073106373") == "1073106373"
    assert NPI.normalize("NPI: 1073106373") == "1073106373"

    assert NPI.normalize("NPI banana") is None
    assert NPI.normalize("NPI: 1073106374") is None
    assert NPI.is_valid("1073106373")
    assert not NPI.is_valid("11073106373")
    assert not NPI.is_valid("1073106375")
    assert NPI.is_valid("808401993999998")
    # Wrong length, valid check digit:
    assert not NPI.is_valid("757738475883")
