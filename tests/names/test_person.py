from rigour.names.person import remove_person_prefixes

def test_remove_person_prefixes():
    assert remove_person_prefixes('Mr. John Doe') == 'John Doe'
    assert remove_person_prefixes('Lady Buckethead') == 'Buckethead'
    assert remove_person_prefixes('LadyBucket') == 'LadyBucket'