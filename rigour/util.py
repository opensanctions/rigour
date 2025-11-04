import gc
import sys
from typing import List
from threading import RLock


MEMO_TINY = 128
MEMO_SMALL = 2000
MEMO_MEDIUM = 20000
MEMO_LARGE = 2**17

resource_lock = RLock()
"""A global lock for resource-intensive operations, meant to avoid race conditions
in loading large resource files."""


def unload_module(module_name: str) -> None:
    """Unload a module from sys.modules, if it is loaded.

    Args:
        module_name: The name of the module to unload.
    """
    mod = sys.modules.pop(module_name, None)
    if mod is not None:
        del mod
    gc.collect()


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
