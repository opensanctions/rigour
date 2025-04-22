from itertools import combinations
from collections import defaultdict
from typing import Dict, Optional, List
from normality import ascii_text
from rigour.text.distance import levenshtein
from rigour.text.scripts import is_latin_char, is_modern_alphabet_char


def latin_share(text: str) -> float:
    """Determine the percentage of a string that's latin."""
    latin = 0.0
    for char in text:
        if is_latin_char(char):
            latin += 1.0
        elif is_modern_alphabet_char(char):
            latin += 0.1
    return latin / max(1, len(text))


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
        form = name.strip().lower()
        if len(form) == 0:
            continue
        # even totally non-Latin names have a base weight of 1:
        latin_shr = latin_share(name)
        if latin_shr > 0.9:
            latin_names.append(name)
        weight = 1 + latin_shr
        weights[form] += weight
        forms[form].append(name)
        forms[form].append(name.title())

        norm = ascii_text(form)
        if norm is not None and len(norm):
            weights[norm] += weight
            forms[norm].append(name)

    if len(latin_names) == 1:
        return latin_names[0]

    for form in levenshtein_pick(list(weights.keys()), weights):
        for surface in levenshtein_pick(forms.get(form, []), {}):
            if surface in names:
                return surface
    return None


def pick_case(names: List[str]) -> Optional[str]:
    """Pick the best mix of lower- and uppercase characters from a set of names
    that are identical except for case.

    Args:
        names (List[str]): A list of identical names in different cases.

    Returns:
        Optional[str]: The best name for display.
    """
    if len(names) == 0:
        return None
    if len(names) == 1:
        return names[0]
    reference = names[0].title()
    difference: Dict[str, int] = {n: 0 for n in names}
    for i, char in enumerate(reference):
        for name in names:
            if name[i] != char:
                difference[name] += 1
    return min(difference.items(), key=lambda x: x[1])[0]
