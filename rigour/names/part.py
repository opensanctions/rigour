from typing import Optional, List, Any
from functools import cached_property
from normality import ascii_text, WS

from rigour.text.scripts import is_modern_alphabet
from rigour.text.phonetics import metaphone
from rigour.names.tokenize import prepare_tokenize_name
from rigour.names.person import remove_person_prefixes


class NamePart(object):
    """A part of a name, such as a given name or family name. This 
    object is used to compare and match names. It stores representations
    of the name in various processing forms."""

    # __slots__ = ["name", "lower", "index", "metaphone", "is_alphabet", "ascii"]

    def __init__(self, name: str, index: Optional[int] = None) -> None:
        self.name = name
        self.lower = name.lower()
        self.index = index
        # TODO: add type - e.g. given, family, etc.
        # TODO: add language
        # TODO: add script

    @cached_property
    def is_alphabet(self) -> bool:
        return is_modern_alphabet(self.name)

    @cached_property
    def ascii(self) -> Optional[str]:
        return ascii_text(self.lower)

    @cached_property
    def metaphone(self) -> Optional[str]:
        if self.is_alphabet and self.ascii is not None:
            # doesn't handle non-ascii characters
            out = metaphone(self.ascii)
            if len(out) >= 3:
                return out
        return None

    def __eq__(self, other: Any) -> bool:
        try:
            return not other.lower != self.lower
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return hash(self.lower)

    def __len__(self) -> int:
        return len(self.name)

    def __repr__(self) -> str:
        return "<NamePart(%s, %s)>" % (self.name, self.index)


def name_parts(
    name: str, person: bool = True, organisation: bool = True
) -> List[NamePart]:
    """Split a name into parts, and return a list of NamePart objects."""
    name = prepare_tokenize_name(name)
    if person:
        name = remove_person_prefixes(name)
    parts = name.split(WS)
    # TODO: remove person name prefixes
    # TODO: chunk down organisation legal forms
    return [NamePart(part, index=i) for i, part in enumerate(parts) if len(part)]
