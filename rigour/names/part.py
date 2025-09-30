from typing import Any, List, Optional

from normality import ascii_text
from rigour.text.scripts import can_latinize
from rigour.text.phonetics import metaphone
from rigour.text.numbers import string_number
from rigour.names.tag import NamePartTag
from rigour.names.symbol import Symbol
from rigour.names.tag import NAME_TAGS_ORDER


class NamePart(object):
    """A part of a name, such as a given name or family name. This object is used to compare
    and match names. It generates and caches representations of the name in various processing
    forms."""

    __slots__ = ["form", "index", "tag", "latinize", "numeric", "_ascii", "_hash"]

    def __init__(
        self,
        form: str,
        index: Optional[int] = None,
        tag: NamePartTag = NamePartTag.UNSET,
    ) -> None:
        self.form = form
        self.index = index

        self.tag = tag
        """Part tag, see NamePartTag."""

        self.latinize = can_latinize(form)
        """Whether this part can be latinized."""

        self.numeric = form.isnumeric()
        """Whether this part is numeric."""

        self._ascii: Optional[str] = None
        self._hash = hash((self.index, self.form))

    @property
    def ascii(self) -> Optional[str]:
        if self._ascii is None:
            if self.numeric:
                value = self.integer
                if value is not None:
                    self._ascii = str(value)
                    return self._ascii
            out = ascii_text(self.form)
            self._ascii = "".join(o for o in out if o.isalnum())
        return self._ascii if len(self._ascii) > 0 else None

    @property
    def integer(self) -> Optional[int]:
        if self.numeric:
            numeric = string_number(self.form)
            if numeric is not None and numeric.is_integer():
                return int(numeric)
        return None

    @property
    def comparable(self) -> str:
        if self.numeric:
            return str(self.integer)
        if not self.latinize:
            return self.form
        ascii = self.ascii
        if ascii is None:
            return self.form
        return ascii

    @property
    def metaphone(self) -> Optional[str]:
        if self.latinize and not self.numeric:
            text = self.ascii
            if text is not None and len(text) > 2:
                return metaphone(text)
        return None

    def can_match(self, other: "NamePart") -> bool:
        """Check if this part can match another part. This is based on the tags of the parts."""
        return self.tag.can_match(other.tag)

    def __eq__(self, other: Any) -> bool:
        try:
            return other._hash == self._hash  # type: ignore
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return self._hash

    def __len__(self) -> int:
        return len(self.form)

    def __repr__(self) -> str:
        return "<NamePart(%r, %s, %r)>" % (self.form, self.index, self.tag.value)

    @classmethod
    def tag_sort(cls, parts: list["NamePart"]) -> list["NamePart"]:
        """Sort name parts by their index."""
        return sorted(parts, key=lambda np: NAME_TAGS_ORDER.index(np.tag))


class Span:
    """A span is a set of parts of a name that have been tagged with a symbol."""

    __slots__ = ["parts", "symbol"]

    def __init__(self, parts: List[NamePart], symbol: Symbol) -> None:
        self.parts = tuple(parts)
        self.symbol = symbol

    @property
    def comparable(self) -> str:
        """Return the comparison-suited string representation of the span."""
        return " ".join([part.comparable for part in self.parts])

    # @property
    # def numeric(self) -> bool:
    #     """Return whether all parts in the span are numeric."""
    #     if len(self.parts) != 1:
    #         return False
    #     return self.parts[0].numeric

    def __len__(self) -> int:
        """Return the number of parts in the span."""
        return sum(len(part) for part in self.parts)

    def __hash__(self) -> int:
        return hash((self.parts, self.symbol))

    def __eq__(self, other: Any) -> bool:
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        return f"<Span({self.parts!r}, {self.symbol})>"
