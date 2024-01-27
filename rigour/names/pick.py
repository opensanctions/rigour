from itertools import combinations
from collections import defaultdict
from typing import Dict, Optional, List, Tuple
from fingerprints.cleanup import clean_name_ascii
from rigour.text.distance import levenshtein
from rigour.text.scripts import is_latin


def latin_share(text: str) -> float:
    """Determine the percentage of a string that's latin."""
    latin = 0
    for char in text:
        if is_latin(char):
            latin += 1
    return latin / max(1, len(text))


def pick_name(names: List[str]) -> Optional[str]:
    """Pick the best name from a list of names. This is meant to pick a centroid
    name, with a bias towards names in a latin script.
    
    Args:
        names (List[str]): A list of names.
        
    Returns:
        Optional[str]: The best name for display.
    """
    forms: List[Tuple[str, str, float]] = []
    for name in sorted(names):
        norm = clean_name_ascii(name)
        if norm is not None:
            weight = 2 - latin_share(name)
            forms.append((norm, name, weight))
            forms.append((norm.title(), name, weight))

    edits: Dict[str, float] = defaultdict(float)
    for ((l_norm, left, l_weight), (r_norm, right, r_weight)) in combinations(forms, 2):
        distance = levenshtein(l_norm, r_norm)
        edits[left] += distance * l_weight
        edits[right] += distance * r_weight

    for cand, _ in sorted(edits.items(), key=lambda x: x[1]):
        return cand
    return None
