from functools import cached_property
from typing import Any, Optional

from normality import ascii_text
from rigour.text.scripts import is_modern_alphabet
from rigour.text.phonetics import metaphone
from rigour.names.tag import NamePartTag
from rigour.names.tag import FAMILY_NAME_TAGS, GIVEN_NAME_TAGS, NAME_TAGS_ORDER


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
        out = ascii_text(self.form)
        if out is None:
            return None
        return "".join(o for o in out if o.isalnum())

    @property
    def maybe_ascii(self) -> str:
        if not self.is_modern_alphabet:
            return self.form
        if self.ascii is None:
            return self.form
        return self.ascii

    @property
    def metaphone(self) -> Optional[str]:
        if self.is_modern_alphabet and self.ascii is not None:
            # doesn't handle non-ascii characters
            return metaphone(self.ascii)
        return None

    def can_match(self, other: "NamePart") -> bool:
        """Check if this part can match another part. This is based on the tags of the parts."""
        if NamePartTag.ANY in (self.tag, other.tag):
            return True
        if self.tag in GIVEN_NAME_TAGS and other.tag not in GIVEN_NAME_TAGS:
            return False
        if self.tag in FAMILY_NAME_TAGS and other.tag not in FAMILY_NAME_TAGS:
            return False
        return True

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

    @classmethod
    def tag_sort(cls, parts: list["NamePart"]) -> list["NamePart"]:
        """Sort name parts by their index."""
        return sorted(parts, key=lambda np: NAME_TAGS_ORDER.index(np.tag))
