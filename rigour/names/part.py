from functools import cached_property
from typing import Any, Optional

from normality import ascii_text
from rigour.text.scripts import is_modern_alphabet
from rigour.text.phonetics import metaphone
from rigour.names.tag import NamePartTag


class NamePart(object):
    """A part of a name, such as a given name or family name. This object is used to compare
    and match names. It generates and caches representations of the name in various processing
    forms."""

    #  __slots__ = ["form", "index", "tag"]

    def __init__(
        self,
        form: str,
        index: Optional[int] = None,
        tag: NamePartTag = NamePartTag.ANY,
    ) -> None:
        self.form = form
        self.index = index
        self.tag = tag

    @cached_property
    def is_modern_alphabet(self) -> bool:
        return is_modern_alphabet(self.form)

    @cached_property
    def ascii(self) -> Optional[str]:
        return ascii_text(self.form)

    @property
    def metaphone(self) -> Optional[str]:
        if self.is_modern_alphabet and self.ascii is not None:
            # doesn't handle non-ascii characters
            return metaphone(self.ascii)
        return None

    def __eq__(self, other: Any) -> bool:
        try:
            return other.form == self.form and other.index == self.index  # type: ignore
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return hash((self.index, self.form))

    def __len__(self) -> int:
        return len(self.form)

    def __repr__(self) -> str:
        return "<NamePart(%r, %s, %r)>" % (self.form, self.index, self.tag.value)
