from enum import Enum
from typing import Any


class Symbol:
    """A symbol is a semantic interpretation applied to one or more parts of a name. Symbols can
    represent various categories such as organization classes, initials, names, numeric, or phonetic
    transcriptions. Each symbol has a category and an identifier."""

    class Category(Enum):
        # ORG_TYPE = "ORGTYPE"
        ORG_CLASS = "ORGCLS"
        SYMBOL = "SYMBOL"
        DOMAIN = "DOMAIN"
        INITIAL = "INITIAL"
        NAME = "NAME"
        NICK = "NICK"
        NUMERIC = "NUM"
        LOCATION = "LOC"
        PHONETIC = "PHON"

    __slots__ = ["category", "id"]

    def __init__(self, category: Category, id: Any) -> None:
        """Create a symbol with a category and an id."""
        self.category = category
        self.id = id

    def __hash__(self) -> int:
        return hash((self.category, self.id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self.category == other.category and self.id == other.id

    def __str__(self) -> str:
        return f"[{self.category.value}:{self.id}]"

    def __repr__(self) -> str:
        return f"<Symbol({self.category}, {self.id})>"
