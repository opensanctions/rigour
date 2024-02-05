from itertools import combinations
from collections import defaultdict
from typing import Dict, Optional, List, Tuple
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


def pick_name(names: List[str]) -> Optional[str]:
    """Pick the best name from a list of names. This is meant to pick a centroid
    name, with a bias towards names in a latin script.
    
    Args:
        names (List[str]): A list of names.
        
    Returns:
        Optional[str]: The best name for display.
    """
    forms: List[Tuple[str, str, float]] = []
    latin_names: List[str] = []
    for name in sorted(names):
        form = name.strip().lower()
        if len(form) == 0:
            continue
        # even totally non-Latin names have a base weight of 1:
        latin_shr = latin_share(name)
        if latin_shr > 0.9:
            latin_names.append(name)
        weight = 1 + (10 * latin_shr)
        forms.append((form, name, weight))

        norm = ascii_text(form)
        if norm is not None and len(norm):
            forms.append((norm, name, weight))

    if len(latin_names) == 1:
        return latin_names[0]
    
    edits: Dict[str, float] = defaultdict(float)
    for ((l_norm, left, l_weight), (r_norm, right, r_weight)) in combinations(forms, 2):
        distance = levenshtein(l_norm, r_norm)
        edits[left] += distance * l_weight
        edits[right] += distance * r_weight

    for cand, _ in sorted(edits.items(), key=lambda x: x[1], reverse=True):
        return cand
    return None
