from typing import Dict, Any, List, Optional

from rigour.data.countries.world import WORLD


class Territory(object):
    """A territory - country, sub-national, historic, or supranational."""

    __slots__ = ["world", "code", "name", "full_name", "is_country", "_parent", "_see"]

    def __init__(self, world: "World", code: str, data: Dict[str, Any]) -> None:
        self.world = world
        self.code = code
        self.name: str = data["name"]
        self.full_name: str = data.get("full_name", self.name)
        self.is_country: bool = data.get("country", False)
        self._parent: Optional[str] = data.get("parent")
        self._see: List[str] = data.get("see", [])

    @property
    def parent(self) -> Optional["Territory"]:
        if self._parent is None:
            return None
        if not self.world.has(self._parent):
            msg = "Invalid parent: %s (country: %r)" % (self._parent, self.code)
            raise RuntimeError(msg)
        return self.world.get(self._parent)
    
    @property
    def see(self) -> List["Territory"]:
        return [self.world.get(s) for s in self._see]

    def __repr__(self) -> str:
        return f"<Territory({self.code!r})>"


class World(object):
    """An index of all territories in the world, basically a registry."""

    def __init__(self) -> None:
        self.territories: Dict[str, Territory] = {}
        for code, data in WORLD.items():
            self.territories[code] = Territory(self, code, data)

    def has(self, code: str) -> bool:
        return code in self.territories

    def get(self, code: str) -> Territory:
        return self.territories[code]
