from typing import Optional, List, Dict, Any, Set

from rigour.names.part import NamePart, Span
from rigour.names.symbol import Symbol
from rigour.names.tag import NameTypeTag, NamePartTag
from rigour.names.tokenize import tokenize_name, prenormalize_name
from rigour.util import list_intersection


class Name(object):
    """A name of a thing, such as a person, organization or object. Each name consists of a
    sequence of parts, each of which has a form and a tag. The form is the text of the part, and the tag
    is a label indicating the type of part. For example, in the name "John Smith", "John" is a given name
    and "Smith" is a family name. The tag for "John" would be `NamePartTag.GIVEN` and the tag for "Smith"
    would be `NamePartTag.FAMILY`. The form for both parts would be the text of the part itself.
    """

    __slots__ = ["original", "form", "tag", "lang", "_parts", "spans"]

    def __init__(
        self,
        original: str,
        form: Optional[str] = None,
        tag: NameTypeTag = NameTypeTag.UNK,
        lang: Optional[str] = None,
        parts: Optional[List[NamePart]] = None,
    ):
        self.original = original
        self.form = form or prenormalize_name(original)
        self.tag = tag
        self.lang = lang
        self._parts = parts
        self.spans: List[Span] = []

    @property
    def parts(self) -> List[NamePart]:
        if self._parts is None:
            self._parts = []
            for i, form in enumerate(tokenize_name(self.form)):
                self._parts.append(NamePart(form, i))
        return self._parts

    @property
    def comparable(self) -> str:
        """Return the ASCII representation of the name, if available."""
        return " ".join(part.comparable for part in self.parts)

    @property
    def norm_form(self) -> str:
        """Return the normalized form of the name by joining name parts."""
        return " ".join([part.form for part in self.parts])

    def tag_text(self, text: str, tag: NamePartTag, max_matches: int = 1) -> None:
        tokens = tokenize_name(prenormalize_name(text))
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

    def apply_phrase(self, phrase: str, symbol: Symbol) -> None:
        """Apply a symbol to a phrase in the name."""
        matching: List[NamePart] = []
        tokens = phrase.split(" ")
        for part in self.parts:
            next_token = tokens[len(matching)]
            if part.form == next_token:
                matching.append(part)
            if len(matching) == len(tokens):
                self.spans.append(Span(matching, symbol))
                matching = []

    def apply_part(self, part: NamePart, symbol: Symbol) -> None:
        """Apply a symbol to a part of the name."""
        self.spans.append(Span([part], symbol))

    @property
    def symbols(self) -> Set[Symbol]:
        """Return a dictionary of symbols applied to the name."""
        symbols: Set[Symbol] = set()
        for span in self.spans:
            symbols.add(span.symbol)
        return symbols

    def contains(self, other: "Name") -> bool:
        """Check if this name contains another name."""
        if self == other or self.tag == NameTypeTag.UNK:
            return False
        if len(self.parts) < len(other.parts):
            return False

        if self.tag == NameTypeTag.PER:
            forms = [part.comparable for part in self.parts]
            other_forms = [part.comparable for part in other.parts]
            common_forms = list_intersection(forms, other_forms)

            # we want to make this support middle initials so that
            # "John Smith" can match "J. Smith"
            for ospan in other.spans:
                if ospan.symbol.category == Symbol.Category.INITIAL:
                    if len(ospan.parts[0].form) > 1:
                        continue
                    for span in self.spans:
                        if span.symbol == ospan.symbol:
                            common_forms.append(ospan.comparable)

            # If every part of the other name is represented in the common forms,
            # we consider it a match.
            if len(common_forms) == len(other_forms):
                return True

        return other.norm_form in self.norm_form

    def symbol_map(self) -> Dict[Symbol, List[Span]]:
        """Return a mapping of symbols to their string representations."""
        symbol_map: Dict[Symbol, List[Span]] = {}
        for span in self.spans:
            if span.symbol not in symbol_map:
                symbol_map[span.symbol] = []
            symbol_map[span.symbol].append(span)
        return symbol_map

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
