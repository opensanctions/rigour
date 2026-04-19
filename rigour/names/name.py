from typing import Optional, List, Any, Set, Iterable
import itertools

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

    __slots__ = ["original", "form", "tag", "lang", "parts", "spans"]

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
        self.parts: List[NamePart] = parts or []
        if parts is None:
            for i, form in enumerate(tokenize_name(self.form)):
                self.parts.append(NamePart(form, i))
        self.spans: List[Span] = []

    @property
    def comparable(self) -> str:
        """Return the ASCII representation of the name, if available."""
        return " ".join(part.comparable for part in self.parts)

    @property
    def norm_form(self) -> str:
        """Return the normalized form of the name by joining name parts."""
        return " ".join([part.form for part in self.parts])

    def tag_text(self, text: str, tag: NamePartTag, max_matches: int = 1) -> None:
        """Tags name parts from a text with a known tag type.

        For example, if the name is "John Smith", and we know that "John" is the given name,
        this method will tag that name part with NamePartTag.GIVEN.

        The tagger can skip tokens in the name. For example, if the name is
        "Karl-Theodor Maria Nikolaus zu Guttenberg", and `text` is "Karl-Theodor
        Nikolaus", both "Karl-Theodor" and "Nikolaus" will be tagged, while
        "Maria" will not be tagged.

        If `text` is not matched in full, the tagger will not tag any name parts. For example,
        if the name is "John Smith", and `text` is "John Ted", "John" will not be tagged.

        The tagger will tag up to `max_matches` occurrences of `text` in the name.
        For example, if the name is "John John Smith", and `text` is "John", both
        "John"s will be tagged if `max_matches` is >= 2.
        """
        tokens = tokenize_name(prenormalize_name(text))
        if len(tokens) == 0:
            return

        matches = 0
        matching: List[NamePart] = []
        for part in self.parts:
            next_token = tokens[len(matching)]
            if part.form == next_token:
                matching.append(part)
            # Only tag if we have matched the entire text
            if len(matching) == len(tokens):
                for part in matching:
                    if part.tag == NamePartTag.UNSET:
                        part.tag = tag
                    elif not part.tag.can_match(tag):
                        # if the part is already tagged, we check compatibility and
                        # otherwise mark it as an outcast from polite society
                        part.tag = NamePartTag.AMBIGUOUS
                matches += 1
                if matches >= max_matches:
                    return
                # Reset the list of matching parts, i.e. start over matching from the
                # beginning of the tokenized text if we haven't reached `max_matches`.
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

    @classmethod
    def consolidate_names(cls, names: Iterable["Name"]) -> Set["Name"]:
        """Remove short names that are contained in longer names.

        This is useful when building a matcher to prevent a scenario where a short
        version of a name ("John Smith") is matched to a query ("John K Smith"), where a longer
        version would have disqualified the match ("John K Smith" != "John R Smith").
        """
        # We call these super_names because they are (non-strict) supersets of names.
        super_names = set(names)

        for name, other in itertools.product(names, names):
            # Check if name is still in super_names, otherwise two equal names
            # will remove each other with none being left.
            if name in super_names and name.contains(other):
                # Use discard instead of remove here because other may already have been kicked out
                # by another name of which it was a subset.
                super_names.discard(other)

        return super_names
