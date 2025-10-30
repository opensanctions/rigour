import re
from typing import Tuple
from functools import cache

from rigour.data.names.data import (
    PERSON_NAME_PREFIXES,
    ORG_NAME_PREFIXES,
    OBJ_NAME_PREFIXES,
)


@cache
def re_prefixes(prefixes: Tuple[str, ...]) -> re.Pattern[str]:
    """Compile a regex pattern to match common name prefixes."""
    # e.g. Mr., Mrs., Dr., etc. for people, The for organizations, etc.
    person_name_prefixes = "|".join((re.escape(p) for p in prefixes))
    prefix_pattern = r"^\W*((%s)\.?\s+)*"
    prefix_pattern_ = prefix_pattern % person_name_prefixes
    return re.compile(prefix_pattern_, re.I | re.U)


def remove_person_prefixes(name: str) -> str:
    """Remove prefixes like Mr., Mrs., etc."""
    return re_prefixes(PERSON_NAME_PREFIXES).sub("", name)


def remove_org_prefixes(name: str) -> str:
    """Remove prefixes like "The", etc."""
    return re_prefixes(ORG_NAME_PREFIXES).sub("", name)


def remove_obj_prefixes(name: str) -> str:
    """Remove prefixes like "The", "MV", etc."""
    return re_prefixes(OBJ_NAME_PREFIXES).sub("", name)
