from typing import Optional


class IdentifierFormat(object):
    """Base class for identifier types."""

    TITLE: str = "Generic identifier"
    STRONG: bool = False

    @classmethod
    def is_valid(cls, value: str) -> bool:
        norm = cls.normalize(value)
        return norm is not None and len(norm) > 0

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        return value.strip()

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()
