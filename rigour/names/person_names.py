from typing import Dict, Generator, List, Set, Tuple

from rigour._core import person_names_text
from rigour.text.dictionary import Normalizer, noop_normalizer


def load_person_names() -> Generator[Tuple[str, List[str]], None, None]:
    """Load the person QID to name mappings from the embedded corpus.
    This is a collection of aliases (in various alphabets) of person
    name parts mapped to a group ID — typically a Wikidata QID, with a
    small tail of X-prefixed manual override IDs.

    The corpus lives in the Rust crate (plain
    `rust/data/names/person_names.txt` at build time, zstd-compressed
    into the binary by `build.rs`, decoded on first access by
    `rigour._core.person_names_text()`). The Rust side goes through
    one UTF-8 PyString allocation for the full ~8.5 MB on each call,
    so callers should iterate this generator to completion rather than
    restarting mid-stream.

    Returns:
        Generator[Tuple[str, List[str]], None, None]: a generator
        yielding tuples of group ID and list of name aliases.
    """
    text = person_names_text()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        names_, gid = line.split(" => ")
        names = names_.split(", ")
        yield gid, names


def load_person_names_mapping(
    normalizer: Normalizer = noop_normalizer, min_mappings: int = 1
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
