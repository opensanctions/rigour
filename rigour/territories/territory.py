from typing import Dict, Any, List, Optional

from rigour.ids.wikidata import is_qid


class Territory(object):
    """A territory - country, sub-national, historic, or supranational."""

    def __init__(
        self, index: Dict[str, "Territory"], code: str, data: Dict[str, Any]
    ) -> None:
        self.index = index
        self.code = code
        self.name: str = data["name"]
        self.full_name: str = data.get("full_name", self.name)
        self.is_country: bool = data.get("is_country", False)
        self.is_ftm: bool = data.get("is_ftm", False)
        self.is_jurisdiction: bool = data.get("is_jurisdiction", self.is_country)
        self.qid: str = str(data.get("qid"))
        self.other_qids: List[str] = data.get("other_qids", [])
        self._parent: Optional[str] = data.get("parent")
        self._see: List[str] = data.get("see", [])

    def _validate(self) -> None:
        assert self.code is not None, f"Missing code: {self.name}"
        assert self.qid is not None, f"Missing QID: {self.code}"
        assert is_qid(self.qid), f"Invalid QID: {self.code}"
        for other_qid in self.other_qids:
            assert is_qid(other_qid), f"Invalid QID: {other_qid}"
        if self._parent is not None:
            if self._parent not in self.index:
                msg = "Invalid parent: %s (country: %r)" % (self._parent, self.code)
                raise RuntimeError(msg)

    @property
    def parent(self) -> Optional["Territory"]:
        """Return the governing territory."""
        if self._parent is None:
            return None
        return self.index[self._parent]

    @property
    def ftm_country(self) -> Optional[str]:
        """Return the FTM country code for this territory."""
        if self.is_ftm:
            return self.code
        if self.parent is not None:
            return self.parent.ftm_country
        return None

    @property
    def see(self) -> List["Territory"]:
        """Return a list of related territories."""
        return [self.index[s] for s in self._see]

    def __repr__(self) -> str:
        return f"<Territory({self.code!r})>"
