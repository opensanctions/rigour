import re
from functools import cache
from typing import Generator, List, Tuple

from rigour.data import DATA_PATH
from rigour.data.names.data import PERSON_NAME_PREFIXES

NAMES_DATA_PATH = DATA_PATH / "names" / "persons.txt"


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


def load_person_names() -> Generator[Tuple[str, List[str]], None, None]:
    """Load the person QID to name mappings from disk. This is a collection
    of aliases (in various alphabets) of person name parts mapped to a
    Wikidata QID representing that name part."""
    with open(NAMES_DATA_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            names_, qid = line.split(" => ")
            names = names_.split(", ")
            yield qid, names
