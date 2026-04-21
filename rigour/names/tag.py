"""Name-tag enums — `NameTypeTag` (person/org/entity/object/unknown)
and `NamePartTag` (given/family/middle/etc.) — plus the helper sets
used by the tagging and sorting pipelines.

Rust-backed via `rigour._core.NameTypeTag` / `NamePartTag`. The
Python-side surface preserves the pre-port constants exactly —
downstream code can keep importing `INITIAL_TAGS`, `WILDCARDS`,
`GIVEN_NAME_TAGS`, `FAMILY_NAME_TAGS`, `NAME_TAGS_ORDER` from here
without change.

`NamePartTag.can_match` is now a native Rust method; the Python
sets below mirror the equivalent Rust constants in
`rust/src/names/tag.rs` and are rebuilt here for the membership
checks downstream code performs (e.g. `part.tag in INITIAL_TAGS`).
"""
from rigour._core import NamePartTag, NameTypeTag

__all__ = [
    "NamePartTag",
    "NameTypeTag",
    "WILDCARDS",
    "INITIAL_TAGS",
    "GIVEN_NAME_TAGS",
    "FAMILY_NAME_TAGS",
    "NAME_TAGS_ORDER",
]


WILDCARDS = frozenset(
    {
        NamePartTag.UNSET,
        NamePartTag.AMBIGUOUS,
        NamePartTag.STOP,
    }
)

INITIAL_TAGS = frozenset(
    {
        NamePartTag.GIVEN,
        NamePartTag.MIDDLE,
        NamePartTag.PATRONYMIC,
        NamePartTag.MATRONYMIC,
    }
)

GIVEN_NAME_TAGS = frozenset(
    {
        NamePartTag.GIVEN,
        NamePartTag.MIDDLE,
        NamePartTag.PATRONYMIC,
        NamePartTag.MATRONYMIC,
        NamePartTag.HONORIFIC,
        NamePartTag.STOP,
        NamePartTag.NICK,
    }
)

FAMILY_NAME_TAGS = frozenset(
    {
        NamePartTag.PATRONYMIC,
        NamePartTag.MATRONYMIC,
        NamePartTag.FAMILY,
        NamePartTag.SUFFIX,
        NamePartTag.TRIBAL,
        NamePartTag.HONORIFIC,
        NamePartTag.NUM,
        NamePartTag.STOP,
    }
)

NAME_TAGS_ORDER = (
    NamePartTag.HONORIFIC,
    NamePartTag.TITLE,
    NamePartTag.GIVEN,
    NamePartTag.MIDDLE,
    NamePartTag.NICK,
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
    NamePartTag.UNSET,
    NamePartTag.AMBIGUOUS,
    NamePartTag.FAMILY,
    NamePartTag.TRIBAL,
    NamePartTag.NUM,
    NamePartTag.SUFFIX,
    NamePartTag.LEGAL,
    NamePartTag.STOP,
)
