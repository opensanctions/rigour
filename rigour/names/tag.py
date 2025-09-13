from enum import Enum


class NameTypeTag(Enum):
    """Metadata on what sort of object is described by a name"""

    UNK = "UNK"  # Unknown
    ENT = "ENT"  # Entity
    PER = "PER"  # Person
    ORG = "ORG"  # Organization/Company
    OBJ = "OBJ"  # Object - Vessel, Security, etc.


class NamePartTag(Enum):
    """Within a name, identify name part types."""

    UNSET = "UNSET"
    AMBIGUOUS = "AMBIGUOUS"

    TITLE = "TITLE"
    GIVEN = "GIVEN"
    MIDDLE = "MIDDLE"
    FAMILY = "FAMILY"
    TRIBAL = "TRIBAL"
    PATRONYMIC = "PATRONYMIC"
    MATRONYMIC = "MATRONYMIC"
    HONORIFIC = "HONORIFIC"
    SUFFIX = "SUFFIX"
    NICK = "NICK"

    STOP = "STOP"  # Stopword
    NUM = "NUM"
    LEGAL = "LEGAL"  # Legal form of an organisation

    def can_match(self, other: "NamePartTag") -> bool:
        """Check if this tag can match the other tag."""
        if self in WILDCARDS or other in WILDCARDS:
            return True
        if self == other:
            return True
        if self in GIVEN_NAME_TAGS and other not in GIVEN_NAME_TAGS:
            return False
        if self in FAMILY_NAME_TAGS and other not in FAMILY_NAME_TAGS:
            return False
        return True


WILDCARDS = {
    NamePartTag.UNSET,
    NamePartTag.AMBIGUOUS,
    NamePartTag.STOP,
}
INTITIAL_TAGS = {
    NamePartTag.GIVEN,
    NamePartTag.MIDDLE,
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
}
GIVEN_NAME_TAGS = {
    NamePartTag.GIVEN,
    NamePartTag.MIDDLE,
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
    NamePartTag.HONORIFIC,
    NamePartTag.STOP,
    NamePartTag.NICK,
}
FAMILY_NAME_TAGS = {
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
    NamePartTag.FAMILY,
    NamePartTag.SUFFIX,
    NamePartTag.TRIBAL,
    NamePartTag.HONORIFIC,
    NamePartTag.NUM,
    NamePartTag.STOP,
}

# All models are lies, but some are useful.
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

UNORDERED = set(list(NamePartTag)) - set(NAME_TAGS_ORDER)
assert len(UNORDERED) == 0, UNORDERED
