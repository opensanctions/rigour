from rigour.names.person import remove_person_prefixes, load_person_names_mapping


def test_remove_person_prefixes():
    assert remove_person_prefixes("Mr. John Doe") == "John Doe"
    assert remove_person_prefixes("Mr John Doe") == "John Doe"
    assert remove_person_prefixes("Lady Buckethead") == "Buckethead"
    assert remove_person_prefixes("LadyBucket") == "LadyBucket"


def test_load_person_names_mapping():
    mapping = load_person_names_mapping()
    assert len(mapping) > 0
    assert len(mapping) > 100000
    assert len(mapping["john"]) > 0
    assert len(mapping["catherine"]) > 0

    # filtered out by the wikidata crawler:
    assert "a" not in mapping
