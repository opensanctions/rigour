import re

QID = re.compile(r"^Q(\d+)$")


def is_qid(text: str) -> bool:
    """Determine if the given string is a valid wikidata QID."""
    return QID.match(text) is not None
