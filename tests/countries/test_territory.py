import pytest

from rigour.countries import world
from rigour.countries.territory import Territory, World


def test_territory_init():
    world = World()
    data = {
        "name": "Test Territory",
        "full_name": "Republic of Test Territory",
        "country": True,
    }
    territory = Territory(world, "TT", data)
    assert territory.code == "TT"
    assert territory.name == "Test Territory"
    assert territory.full_name == "Republic of Test Territory"
    assert territory.is_country is True
    assert territory.parent is None
    assert territory.see == []


def test_world_real():
    assert len(world.territories) > 0
    assert world.has("gb") is True
    assert world.get("gb").name == "United Kingdom"
    assert world.has("gb-nir") is True
    assert world.get("gb-nir").parent == world.get("gb")


def test_territory_repr():
    world = World()
    data = {"name": "Test Territory", "full_name": "Test Territory", "is_country": True}
    territory = Territory(world, "tt", data)
    assert repr(territory) == "<Territory('tt')>"


def test_world_has():
    world = World()
    data = {"name": "Test Territory", "full_name": "Test Territory", "is_country": True}
    territory = Territory(world, "tt", data)
    world.territories["tt"] = territory
    assert world.has("tt") is True
    assert world.has("xx") is False


def test_world_get():
    world = World()
    data = {"name": "Test Territory", "full_name": "Test Territory", "is_country": True}
    territory = Territory(world, "tt", data)
    world.territories["tt"] = territory
    assert world.get("tt") == territory
    with pytest.raises(KeyError):
        world.get("xx")
