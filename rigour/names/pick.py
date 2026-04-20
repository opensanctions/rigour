from typing import Optional, List

from rigour._core import pick_name as pick_name
from rigour._core import reduce_names as reduce_names
from rigour.langs import LangStr, PREFERRED_LANG, PREFERRED_LANGS


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

    Rust-backed via :func:`rigour._core.pick_case`. The Rust
    implementation returns `None` for empty input; this Python wrapper
    raises `ValueError` to preserve the pre-port contract that
    external callers rely on.

    Args:
        names (List[str]): A list of identical names in different cases.

    Returns:
        str: The best name for display.
    """
    from rigour._core import pick_case as _pick_case

    result = _pick_case(names)
    if result is None:
        raise ValueError("Cannot pick a name from an empty list.")
    return result
