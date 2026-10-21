from rigour.names.prefix import (
    remove_obj_prefixes,
    remove_org_prefixes,
    remove_person_prefixes,
)


def test_remove_person_prefixes():
    assert remove_person_prefixes("Mr. John Doe") == "John Doe"
    assert remove_person_prefixes("Pvty Doe") == "Pvty Doe"
    assert remove_person_prefixes("Mr John Doe") == "John Doe"
    assert remove_person_prefixes("Lady Buckethead") == "Buckethead"
    assert remove_person_prefixes("LadyBucket") == "LadyBucket"


def test_remove_org_prefixes():
    assert remove_org_prefixes("The Charitable Trust") == "Charitable Trust"
    assert remove_obj_prefixes("M/V Oceanic") == "Oceanic"


def test_remove_obj_prefixes():
    assert remove_obj_prefixes("M.V. Oceanic") == "Oceanic"
    assert remove_obj_prefixes("m v oceanic") == "oceanic"
    assert remove_obj_prefixes("M/T Oceanic") == "Oceanic"
    assert remove_obj_prefixes("mt oceanic") == "oceanic"
    assert remove_obj_prefixes("SS Oceanic") == "Oceanic"
    assert remove_obj_prefixes("Mtwara Dawn") == "Mtwara Dawn"
