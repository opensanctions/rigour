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
    """Strip honorific prefixes from the head of a person name.

    Drops `"Mr."`, `"Mrs."`, `"Dr."`, `"Lady"`, etc. so honorifics
    don't contaminate part alignment in matching or token-bag
    comparison. The list is data-driven from
    `resources/names/stopwords.yml::PERSON_NAME_PREFIXES`,
    surfaced via `rigour._core.person_name_prefixes_list`.

    Args:
        name: A person name string.

    Returns:
        The name with any leading honorific(s) removed. Idempotent
        for inputs that don't start with a known prefix.
    """
    return _person_prefix_regex().sub("", name)


def remove_org_prefixes(name: str) -> str:
    """Strip article-like prefixes from the head of an organisation name.

    Drops `"The"`, etc. so `"The Charitable Trust"` →
    `"Charitable Trust"` doesn't penalise the shorter variant
    when matching. Driven by
    `resources/names/stopwords.yml::ORG_NAME_PREFIXES`.

    Args:
        name: An organisation name string.

    Returns:
        The name with any leading article-prefix(es) removed.
    """
    return _org_prefix_regex().sub("", name)


def remove_obj_prefixes(name: str) -> str:
    """Strip vessel-class and generic-article prefixes from the
    head of an object name.

    Drops `"M/V"`, `"SS"`, `"The"`, etc. so `"M/V Oceanic"` →
    `"Oceanic"` doesn't penalise the shorter variant when
    matching vessels, vehicles, or aircraft. Driven by
    `resources/names/stopwords.yml::OBJ_NAME_PREFIXES`.

    Args:
        name: An object (vessel / vehicle / aircraft) name string.

    Returns:
        The name with any leading prefix(es) removed.
    """
    return _obj_prefix_regex().sub("", name)
