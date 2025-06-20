from typing import Dict, Generator, List, Set, Tuple

from rigour.data import DATA_PATH
from rigour.text.dictionary import Normalizer, noop_normalizer

NAMES_DATA_PATH = DATA_PATH / "names" / "persons.txt"


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
            names_, qid = line.split(" => ")
            names = names_.split(", ")
            yield qid, names


def load_person_names_mapping(
    normalizer: Normalizer = noop_normalizer,
) -> Dict[str, Set[str]]:
    """Load the person QID to name mappings from disk. This is a collection
    of aliases (in various alphabets) of person name parts mapped to a
    Wikidata QID representing that name part.

    Args:
        normalizer (Normalizer, optional): A function to normalize names. Defaults to noop_normalizer.

    Returns:
        Dict[str, Set[str]]: A dictionary mapping normalized names to sets of QIDs.
    """
    names: Dict[str, Set[str]] = {}
    for qid, aliases in load_person_names():
        for alias in aliases:
            norm_alias = normalizer(alias)
            if norm_alias is None:
                continue
            if norm_alias not in names:
                names[norm_alias] = set([qid])
            else:
                names[norm_alias].add(qid)
    return names
