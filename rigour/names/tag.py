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

    ANY = "ANY"

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


GIVEN_NAME_TAGS = {
    NamePartTag.GIVEN,
    NamePartTag.MIDDLE,
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
    NamePartTag.HONORIFIC,
    # NamePartTag.NICK,
}
FAMILY_NAME_TAGS = {
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
    NamePartTag.FAMILY,
    NamePartTag.SUFFIX,
    NamePartTag.TRIBAL,
    NamePartTag.HONORIFIC,
    NamePartTag.NUM,
}

# All models are lies, but some are useful.
NAME_TAGS_ORDER = (
    NamePartTag.HONORIFIC,
    NamePartTag.GIVEN,
    NamePartTag.MIDDLE,
    NamePartTag.NICK,
    NamePartTag.PATRONYMIC,
    NamePartTag.MATRONYMIC,
    NamePartTag.ANY,
    NamePartTag.FAMILY,
    NamePartTag.TRIBAL,
    NamePartTag.NUM,
    NamePartTag.SUFFIX,
    NamePartTag.LEGAL,
)
