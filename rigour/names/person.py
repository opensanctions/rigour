import re
from rigour.data.names.data import PERSON_NAME_PREFIXES

PERSON_NAME_PREFIXES_ = "|".join(PERSON_NAME_PREFIXES)
PREFIX_PATTERN_ = r"^\W*((%s)\.?\s+)*"
PREFIX_PATTERN_ = PREFIX_PATTERN_ % PERSON_NAME_PREFIXES_
PREFIXES = re.compile(PREFIX_PATTERN_, re.I | re.U)


def remove_person_prefixes(name: str) -> str:
    """Remove prefixes like Mr., Mrs., etc."""
    return PREFIXES.sub("", name)
