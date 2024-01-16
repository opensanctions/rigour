from typing import Optional
from stdnum import imo, isin, iban, figi, bic, lei  # type: ignore
from stdnum.ru import inn  # type: ignore

from rigour.ids.common import StdnumType


class IMO(StdnumType):
    """An IMO number for a ship."""

    TITLE = "IMO"

    impl = imo


class ISIN(StdnumType):
    """An ISIN number for a security."""

    TITLE = "ISIN"

    impl = isin

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class IBAN(StdnumType):
    """An IBAN number for a bank account."""

    TITLE = "IBAN"

    impl = iban


class FIGI(StdnumType):
    """A FIGI number for a security, as managed by OpenFIGI."""

    TITLE = "FIGI"

    impl = figi

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class BIC(StdnumType):
    """BIC (ISO 9362 Business identifier codes)."""

    TITLE = "BIC"

    impl = bic

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        norm = super().normalize(value)
        if norm is not None:
            norm = norm[:8]
        return norm


class INN(StdnumType):
    """Russian tax identification number."""

    TITLE = "INN"

    impl = inn

    @classmethod
    def format(cls, value: str) -> str:
        return value


class LEI(StdnumType):
    """Legal Entity Identifier (ISO 17442)"""

    TITLE = "LEI"

    impl = lei

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()
