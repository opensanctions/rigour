from typing import List


MEMO_SMALL = 2000
MEMO_MEDIUM = 20000
MEMO_LARGE = 2**17


def gettext(text: str) -> str:
    """Placeholder for internationalisation function."""
    return text


def list_intersection(left: List[str], right: List[str]) -> List[str]:
    """Return the number of elements in the intersection of two lists, accounting
    properly for duplicates."""
    overlap: List[str] = []
    remainder = list(right)
    for elem in left:
        try:
            remainder.remove(elem)
            overlap.append(elem)
        except ValueError:
            pass
    return overlap
