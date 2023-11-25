from rigour.ids.wikidata import is_qid, WikidataQID


def test_is_qid():
    assert is_qid("Q7747")
    assert not is_qid("q7747")
    assert not is_qid("Q7747B")
    assert not is_qid("banana")


def test_wikidata():
    assert WikidataQID.is_valid("Q7747")
    assert not WikidataQID.is_valid("X7747")
    assert WikidataQID.normalize("X7747") is None
    assert WikidataQID.normalize("") is None
    assert WikidataQID.normalize("Q7747") == "Q7747"
    assert WikidataQID.normalize("https://www.wikidata.org/wiki/Q7747") == "Q7747"
    assert WikidataQID.format("Q7747") == "Q7747"
