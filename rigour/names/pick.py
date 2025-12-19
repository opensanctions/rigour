import logging
from itertools import combinations
from collections import defaultdict
from typing import Dict, Optional, List
from normality import ascii_text

from rigour.langs import LangStr, PREFERRED_LANG, PREFERRED_LANGS
from rigour.names.check import is_name
from rigour.text.distance import levenshtein
from rigour.data.text.scripts import LATIN_CHARS, LATINIZABLE_CHARS

log = logging.getLogger(__name__)


def latin_share(text: str) -> float:
    """Determine the percentage of a string that's latin."""
    latin = 0.0
    skipped = 0
    for char in text:
        cp = ord(char)
        if cp in LATIN_CHARS:
            latin += 1.0
            continue
        elif cp in LATINIZABLE_CHARS:
            latin += 0.3
            continue
        elif not char.isalpha():
            skipped += 1
    return latin / max(1, len(text) - skipped)


def levenshtein_pick(names: List[str], weights: Dict[str, float]) -> List[str]:
    """Pick the best name from a list of names, using a weighted levenshtein distances."""
    if len(names) < 2:
        return names
    edits: Dict[str, float] = defaultdict(float)
    for left, right in combinations(names, 2):
        distance = levenshtein(left, right)
        base = max(len(left), len(right), 1)
        edits[left] += (1 - (distance / base)) * weights.get(left, 1.0)
        edits[right] += (1 - (distance / base)) * weights.get(right, 1.0)
    return [n for (n, _) in sorted(edits.items(), key=lambda x: x[1], reverse=True)]


def pick_name(names: List[str]) -> Optional[str]:
    """Pick the best name from a list of names. This is meant to pick a centroid
    name, with a bias towards names in a latin script.

    Args:
        names (List[str]): A list of names.

    Returns:
        Optional[str]: The best name for display.
    """
    weights: Dict[str, float] = defaultdict(float)
    forms: Dict[str, List[str]] = defaultdict(list)
    latin_names: List[str] = []
    for name in sorted(names):
        form = name.strip().casefold()
        if len(form) == 0:
            continue
        # even totally non-Latin names have a base weight of 1:
        latin_shr = latin_share(name)
        if latin_shr > 0.85:
            latin_names.append(name)
        weight = 1 + latin_shr
        weights[form] += weight
        forms[form].append(name)
        forms[form].append(name.title())

        norm = ascii_text(form)
        if len(norm) > 2:
            weights[norm] += weight
            forms[norm].append(name)

    if len(latin_names) == 1:
        return latin_names[0]

    for form in levenshtein_pick(list(weights.keys()), weights):
        for surface in levenshtein_pick(forms.get(form, []), {}):
            if surface in names:
                return surface
    return None


def pick_lang_name(names: List[LangStr]) -> Optional[str]:
    """Pick the best name from a list of LangStr objects, prioritizing the preferred language.

    Args:
        names (List[LangStr]): A list of LangStr objects with language information.

    Returns:
        Optional[str]: The best name for display.
    """
    if len(names) == 0:
        return None
    preferred = [str(n) for n in names if n.lang == PREFERRED_LANG]
    if len(preferred) > 0:
        picked = pick_name(preferred)
        if picked is not None:
            return picked
    preferred = [str(n) for n in names if n.lang in PREFERRED_LANGS]
    if len(preferred) > 0:
        picked = pick_name(preferred)
        if picked is not None:
            return picked
    return pick_name([str(n) for n in names])


def pick_case(names: List[str]) -> str:
    """Pick the best mix of lower- and uppercase characters from a set of names
    that are identical except for case. If the names are not identical, undefined
    things happen (not recommended).

    Args:
        names (List[str]): A list of identical names in different cases.

    Returns:
        str: The best name for display.
    """
    if len(names) == 0:
        raise ValueError("Cannot pick a name from an empty list.")
    if len(names) == 1:
        return names[0]

    basic = sorted(names, key=len)[0].title()
    if basic in names:
        return basic

    scores: Dict[str, float] = {}
    for name in names:
        new_word = True
        # Bias for shorter names (`ẞ` over `ss`).
        errors = len(name)
        for char in name:
            if not char.isalpha():
                new_word = True
                continue
            if new_word:
                if not char.isupper():
                    errors += 2
                new_word = False
                continue
            if char.isupper():
                errors += 1
        scores[name] = errors / len(name)

    if len(scores) == 0:
        raise ValueError("Names could not be scored: %r" % names)

    return min(scores.items(), key=lambda i: (i[1], len(i[0])))[0]


def reduce_names(names: List[str], require_names: bool = False) -> List[str]:
    """Select a reduced set of names from a list of names. This is used to
    prepare the set of names linked to a person, organization, or other entity
    for publication.

    Args:
        names (List[str]): A list of names.

    Returns:
        List[str]: The reduced list of names.
    """
    if len(names) < 2:
        if require_names:
            return [n for n in names if is_name(n)]
        return names
    lower: Dict[str, List[str]] = defaultdict(list)
    for name in names:
        # Filter names that are not valid (e.g. empty or do not contain any letters)
        if require_names and not is_name(name):
            log.warning("Invalid name found: %r", name)
            continue
        lower[name.casefold()].append(name)
    reduced: List[str] = []
    for group in lower.values():
        try:
            picked = pick_case(group)
            reduced.append(picked)
        except ValueError:
            log.exception("Could not pick name from group: %r", group)
            reduced.extend(group)
    return reduced
