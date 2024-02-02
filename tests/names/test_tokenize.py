from rigour.names.tokenize import prepare_tokenize_name


def test_prepare_tokenize_name():
    assert prepare_tokenize_name('John Doe') == 'john doe'
    assert prepare_tokenize_name('Bond, James Bond') == 'bond james bond'
    assert prepare_tokenize_name('C.I.A.') == 'cia'