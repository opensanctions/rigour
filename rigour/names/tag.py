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

    TILTLE = "TITLE"
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
    LEGAL = "LEGAL"  # Legal form of an organisation
