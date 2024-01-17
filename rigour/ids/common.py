from typing import Optional, Protocol
from stdnum.exceptions import ValidationError  # type: ignore


class IdentifierFormat(object):
    """Base class for identifier types."""

    TITLE: str = "Generic identifier"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        norm = cls.normalize(value)
        return norm is not None and len(norm) > 0

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        return value.strip()

    @classmethod
    def format(cls, value: str) -> str:
        return value


class StdnumImpl(Protocol):
    """Protocol for stdnum implementations."""

    @classmethod
    def is_valid(cls, value: str) -> bool:
        ...  # pragma: no cover

    @classmethod
    def validate(cls, value: str) -> str:
        ...  # pragma: no cover

    @classmethod
    def compact(cls, value: str) -> str:
        ...  # pragma: no cover

    @classmethod
    def format(cls, value: str) -> str:
        ...  # pragma: no cover


class StdnumFormat(IdentifierFormat):
    """Base class for stdnum-based identifier types."""

    impl: StdnumImpl

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return cls.impl.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            value = cls.impl.validate(value)
            return cls.impl.compact(value)
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return cls.impl.format(value)
