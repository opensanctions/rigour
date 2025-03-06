from typing import Optional
from stdnum import isin, iban, figi, bic, lei  # type: ignore
from stdnum.ru import inn  # type: ignore
from stdnum.us import ssn  # type: ignore
from stdnum.br import cpf, cnpj  # type: ignore

from rigour.ids.common import StdnumFormat


class ISIN(StdnumFormat):
    """An ISIN number for a security."""

    TITLE = "ISIN"
    STRONG: bool = True

    impl = isin

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class IBAN(StdnumFormat):
    """An IBAN number for a bank account."""

    TITLE = "IBAN"
    STRONG: bool = True

    impl = iban


class FIGI(StdnumFormat):
    """A FIGI number for a security, as managed by OpenFIGI."""

    TITLE = "FIGI"
    STRONG: bool = True

    impl = figi

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class BIC(StdnumFormat):
    """BIC (ISO 9362 Business identifier codes)."""

    TITLE = "BIC"
    STRONG: bool = True

    impl = bic

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        norm = super().normalize(value)
        if norm is None:
            return None
        norm = norm[:8].upper()
        if cls.is_valid(norm):
            return norm
        return None


class INN(StdnumFormat):
    """Russian tax identification number."""

    TITLE = "INN"

    impl = inn

    @classmethod
    def format(cls, value: str) -> str:
        return value


class LEI(StdnumFormat):
    """Legal Entity Identifier (ISO 17442)"""

    TITLE = "LEI"
    STRONG: bool = True

    impl = lei

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class SSN(StdnumFormat):
    """US Social Security Number"""

    TITLE = "SSN"
    STRONG: bool = False

    impl = ssn

    @classmethod
    def format(cls, value: str) -> str:
        return str(ssn.format(value))


class CPF(StdnumFormat):
    """Cadastro de Pessoas Físicas, Brazilian national identifier"""

    TITLE = "CPF"

    impl = cpf

    @classmethod
    def format(cls, value: str) -> str:
        return str(cpf.format(value))


class CNPJ(StdnumFormat):
    """Cadastro Nacional de Pessoas Jurídicas, Brazilian national companies identifier"""

    TITLE = "CNPJ"
    STRONG: bool = True

    impl = cnpj

    @classmethod
    def format(cls, value: str) -> str:
        return str(cnpj.format(value))
