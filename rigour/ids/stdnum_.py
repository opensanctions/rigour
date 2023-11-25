from typing import Optional
from stdnum import imo, isin, iban, figi, bic, lei  # type: ignore
from stdnum.ru import inn  # type: ignore

from rigour.ids.common import StdnumType


class IMO(StdnumType):
    """An IMO number for a ship."""

    impl = imo


class ISIN(StdnumType):
    """An ISIN number for a security."""

    impl = isin

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class IBAN(StdnumType):
    """An IBAN number for a bank account."""

    impl = iban


class FIGI(StdnumType):
    """A FIGI number for a security."""

    impl = figi

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class BIC(StdnumType):
    """BIC (ISO 9362 Business identifier codes)."""

    impl = bic

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        norm = super().normalize(value)
        if norm is not None:
            norm = norm[:8]
        return norm


class INN(StdnumType):
    """INN (Russian tax identification number)."""

    impl = inn

    @classmethod
    def format(cls, value: str) -> str:
        return value


class LEI(StdnumType):
    """LEI (Legal Entity Identifier)."""

    impl = lei

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()
