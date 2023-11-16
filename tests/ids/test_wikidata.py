from rigour.ids.wikidata import is_qid


def test_is_qid():
    assert is_qid("Q7747")
    assert not is_qid("q7747")
    assert not is_qid("Q7747B")
    assert not is_qid("banana")
