from functools import partial
from typing import Dict, Generator, List, Set, Tuple

from rigour.data import DATA_PATH
from rigour.text.dictionary import Normalizer
from rigour.text.normalize import Normalize, normalize

NAMES_DATA_PATH = DATA_PATH / "names" / "persons.txt"

# Default normalizer for load_person_names_mapping — strip whitespace,
# None and empty → None. Matches the former `noop_normalizer` default.
_strip_normalizer: Normalizer = partial(normalize, flags=Normalize.STRIP)


def load_person_names() -> Generator[Tuple[str, List[str]], None, None]:
    """Load the person QID to name mappings from disk. This is a collection
    of aliases (in various alphabets) of person name parts mapped to a
    Wikidata QID representing that name part.

    Returns:
        Generator[Tuple[str, List[str]], None, None]: A generator yielding tuples of QID and list of names.
    """
    with open(NAMES_DATA_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            names_, gid = line.split(" => ")
            names = names_.split(", ")
            yield gid, names


def load_person_names_mapping(
    normalizer: Normalizer = _strip_normalizer, min_mappings: int = 1
) -> Dict[str, Set[str]]:
    """Load the person QID to name mappings from disk. This is a collection
    of aliases (in various alphabets) of person name parts mapped to a
    Wikidata QID representing that name part.

    Args:
        normalizer (Normalizer, optional): A function to normalize names.
            Defaults to a strip-only normalizer (whitespace trimmed,
            empty/None → None).

    Returns:
        Dict[str, Set[str]]: A dictionary mapping normalized names to sets of QIDs.
    """
    names: Dict[str, Set[str]] = {}
    for gid, aliases in load_person_names():
        forms: Set[str] = set()
        for alias in aliases:
            norm_alias = normalizer(alias)
            if norm_alias is None or not len(norm_alias):
                continue
            forms.add(norm_alias)
        if len(forms) < min_mappings:
            continue
        for form in forms:
            if form not in names:
                names[form] = set([gid])
            else:
                names[form].add(gid)
    return names
