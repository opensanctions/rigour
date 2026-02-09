from rigour.names.split_phrases import contains_split_phrase

def test_contains_split_phrase():
    assert not contains_split_phrase("International Business Machines")
    assert contains_split_phrase("International Business Machines dba IBM")
    # Case-insensitive
    assert contains_split_phrase("International Business Machines DBA IBM")
    # Another phrase
    assert contains_split_phrase("International Business Machines A.K.A. IBM")
    # Contains dba but only as part of a larger word.
    assert not contains_split_phrase("dudbam")
