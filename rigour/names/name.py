from typing import Optional, List, Any

from rigour.names.part import NamePart
from rigour.names.tag import NameTypeTag, NamePartTag
from rigour.names.tokenize import tokenize_name


def to_form(text: str) -> str:
    return text.lower()


class Name(object):
    """A name of a thing, such as a person, organization or object. Each name consists of a
    sequence of parts, each of which has a form and a tag. The form is the text of the part, and the tag
    is a label indicating the type of part. For example, in the name "John Smith", "John" is a given name
    and "Smith" is a family name. The tag for "John" would be `NamePartTag.GIVEN` and the tag for "Smith"
    would be `NamePartTag.FAMILY`. The form for both parts would be the text of the part itself.
    """

    __slots__ = ["original", "form", "tag", "lang", "_parts"]

    def __init__(
        self,
        original: str,
        form: Optional[str] = None,
        tag: NameTypeTag = NameTypeTag.UNK,
        lang: Optional[str] = None,
        parts: Optional[List[NamePart]] = None,
    ):
        self.original = original
        self.form = form or to_form(original)
        self.tag = tag
        self.lang = lang
        self._parts = parts

    @property
    def parts(self) -> List[NamePart]:
        if self._parts is None:
            self._parts = []
            for i, form in enumerate(tokenize_name(self.form)):
                self._parts.append(NamePart(form, i))
        return self._parts

    def tag_text(self, text: str, tag: NamePartTag, max_matches: int = 1) -> None:
        tokens = tokenize_name(to_form(text))
        matches = 0
        matching: List[NamePart] = []
        for part in self.parts:
            if part.tag not in (tag, NamePartTag.ANY):
                matching = []
                continue
            next_token = tokens[len(matching)]
            if part.form == next_token:
                matching.append(part)
            if len(matching) == len(tokens):
                for part in matching:
                    part.tag = tag
                matches += 1
                if matches >= max_matches:
                    return
                matching = []

    def __eq__(self, other: Any) -> bool:
        try:
            return self.form == other.form  # type: ignore
        except AttributeError:
            return False

    def __hash__(self) -> int:
        return hash(self.form)

    def __str__(self) -> str:
        return self.original

    def __repr__(self) -> str:
        return "<Name(%r, %r, %r)>" % (self.original, self.form, self.tag.value)
