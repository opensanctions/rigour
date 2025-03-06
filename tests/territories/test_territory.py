import pytest

from rigour.territories import get_territory, get_territory_by_qid


def test_world_real():
    gb = get_territory("gb")
    assert gb.name == "United Kingdom"
    assert get_territory_by_qid("Q145") == gb
    nir = get_territory("gb-nir")
    assert nir is not None
    assert nir.parent == gb
    assert get_territory("gb-nirvana") is None


def test_territory_repr():
    fr = get_territory("fr")
    assert repr(fr) == "<Territory('fr')>"
