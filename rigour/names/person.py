import re
from functools import cache
from rigour.data.names.data import PERSON_NAME_PREFIXES


@cache
def re_person_prefixes() -> re.Pattern[str]:
    """Compile a regex pattern to match common person prefixes."""
    # e.g. Mr., Mrs., Dr., etc.
    person_name_prefixes = "|".join(PERSON_NAME_PREFIXES)
    prefix_pattern = r"^\W*((%s)\.?\s+)*"
    prefix_pattern_ = prefix_pattern % person_name_prefixes
    return re.compile(prefix_pattern_, re.I | re.U)


def remove_person_prefixes(name: str) -> str:
    """Remove prefixes like Mr., Mrs., etc."""
    return re_person_prefixes().sub("", name)
