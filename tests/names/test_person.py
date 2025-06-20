from typing import Optional
from rigour.names.person import load_person_names_mapping


def test_load_person_names_mapping():
    mapping = load_person_names_mapping()
    assert len(mapping) > 0
    assert len(mapping) > 100000
    assert len(mapping["john"]) > 0
    assert len(mapping["catherine"]) > 0

    # filtered out by the wikidata crawler:
    assert "a" not in mapping

    def banananorm(name: Optional[str]) -> str:
        return "banana"

    mapping = load_person_names_mapping(normalizer=banananorm)
    assert len(mapping) == 1
