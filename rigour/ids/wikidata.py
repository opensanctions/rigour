import re
from typing import Optional

from rigour.ids.common import IdentifierFormat

QID = re.compile(r"^Q(\d+)$")


def is_qid(text: str) -> bool:
    """Determine if the given string is a valid wikidata QID."""
    return QID.match(text) is not None


class WikidataQID(IdentifierFormat):
    """A wikidata item identifier."""

    TITLE: str = "Wikidata QID"
    STRONG: bool = True

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given string is a valid wikidata QID."""
        return is_qid(text)

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Normalize the given string to a valid wikidata QID."""
        text = text.rsplit("/", 1)[-1].strip().upper()
        match = QID.match(text)
        if match is None:
            return None
        return text
