from rigour.names import contains_split_phrase, name_split_phrases


def test_contains_split_phrase():
    assert not contains_split_phrase("International Business Machines")
    assert contains_split_phrase("International Business Machines dba IBM")
    # Case-insensitive
    assert contains_split_phrase("International Business Machines DBA IBM")
    # Another phrase
    assert contains_split_phrase("International Business Machines A.K.A. IBM")
    # Contains dba but only as part of a larger word.
    assert not contains_split_phrase("dudbam")


def test_name_split_phrases():
    phrases = name_split_phrases()
    assert "dba" in phrases
    assert "f/k/a" in phrases
    assert "International" not in phrases
    for phrase in phrases:
        assert contains_split_phrase(f"Foo {phrase} Bar"), phrase
