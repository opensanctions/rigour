import re
from functools import cache
from typing import List

from rigour._core import (
    obj_name_prefixes_list,
    org_name_prefixes_list,
    person_name_prefixes_list,
)


def _build_prefix_regex(prefixes: List[str]) -> re.Pattern[str]:
    escaped = "|".join(re.escape(p) for p in prefixes)
    return re.compile(r"^\W*((%s)\.?\s+)*" % escaped, re.I | re.U)


@cache
def _person_prefix_regex() -> re.Pattern[str]:
    return _build_prefix_regex(person_name_prefixes_list())


@cache
def _org_prefix_regex() -> re.Pattern[str]:
    return _build_prefix_regex(org_name_prefixes_list())


@cache
def _obj_prefix_regex() -> re.Pattern[str]:
    return _build_prefix_regex(obj_name_prefixes_list())


def remove_person_prefixes(name: str) -> str:
    """Remove prefixes like Mr., Mrs., etc."""
    return _person_prefix_regex().sub("", name)


def remove_org_prefixes(name: str) -> str:
    """Remove prefixes like "The", etc."""
    return _org_prefix_regex().sub("", name)


def remove_obj_prefixes(name: str) -> str:
    """Remove prefixes like "The", "MV", etc."""
    return _obj_prefix_regex().sub("", name)
