from typing import Dict, Any, List, Optional, Set
from functools import total_ordering


@total_ordering
class Territory(object):
    """A territory - country, sub-national, historic, or supranational."""

    def __init__(
        self, index: Dict[str, "Territory"], code: str, data: Dict[str, Any]
    ) -> None:
        self.index = index
        self.code = code
        self.name: str = data["name"]
        self.full_name: str = data.get("full_name", self.name)
        self.alpha3: Optional[str] = data.get("alpha3")
        self.is_country: bool = data.get("is_country", False)
        self.is_ftm: bool = data.get("is_ftm", False)
        self.is_jurisdiction: bool = data.get("is_jurisdiction", self.is_country)
        self.is_historical: bool = data.get("is_historical", False)
        self._region: Optional[str] = data.get("region", None)
        self._subregion: Optional[str] = data.get("subregion", None)
        self.qid: str = str(data.get("qid"))
        self.other_qids: List[str] = data.get("other_qids", [])
        self.other_codes: List[str] = data.get("other_codes", [])
        self._successors: List[str] = data.get("successors", [])
        self._parent: Optional[str] = data.get("parent")
        self._see: List[str] = data.get("see", [])

    @property
    def parent(self) -> Optional["Territory"]:
        """Return the governing territory."""
        if self._parent is None:
            return None
        return self.index[self._parent]

    @property
    def region(self) -> Optional[str]:
        """Return the global region name."""
        if self._region:
            return self._region
        if self.parent:
            return self.parent.region
        return None

    @property
    def subregion(self) -> Optional[str]:
        """Return the subregion name."""
        if self._subregion:
            return self._subregion
        if self.parent:
            return self.parent.subregion
        return None

    @property
    def successors(self) -> List["Territory"]:
        """Return a list of successor countries."""
        return [self.index[s] for s in self._successors]

    @property
    def see(self) -> List["Territory"]:
        """Return a list of related territories."""
        return [self.index[s] for s in self._see]

    @property
    def qids(self) -> Set[str]:
        """Return all the QIDs linked to a territory."""
        qids = set(self.other_qids)
        qids.add(self.qid)
        return qids

    @property
    def ftm_country(self) -> Optional[str]:
        """Return the FTM country code for this territory."""
        if self.is_ftm:
            return self.code
        if self.parent is not None:
            return self.parent.ftm_country
        return None

    def __eq__(self, other: Any) -> bool:
        try:
            return self.code == other.code  # type: ignore
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return hash(self.code)

    def __le__(self, other: Any) -> bool:
        try:
            return self.code <= other.code  # type: ignore
        except AttributeError:
            return True

    def __repr__(self) -> str:
        return f"<Territory({self.code!r})>"
