from typing import Optional
from stdnum import isin, iban, figi, bic, lei
from stdnum.ru import inn
from stdnum.us import ssn
from stdnum.br import cpf, cnpj
from stdnum.cn import uscc

from rigour.ids.common import IdentifierFormat
from stdnum.exceptions import ValidationError


class ISIN(IdentifierFormat):
    """An ISIN number for a security."""

    NAME = "isin"
    TITLE = "ISIN"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return isin.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return isin.compact(isin.validate(value))
        except ValidationError:
            return None


class IBAN(IdentifierFormat):
    """An IBAN number for a bank account."""

    NAME = "iban"
    TITLE = "IBAN"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return iban.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return iban.compact(iban.validate(value))
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return iban.format(value)


class FIGI(IdentifierFormat):
    """A FIGI number for a security, as managed by OpenFIGI."""

    NAME = "figi"
    TITLE = "FIGI"
    STRONG = True

    impl = figi

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return figi.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return figi.compact(figi.validate(value))
        except ValidationError:
            return None


class BIC(IdentifierFormat):
    """BIC (ISO 9362 Business identifier codes)."""

    NAME = "bic"
    TITLE = "BIC"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return bic.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            norm = bic.compact(bic.validate(value))
            norm = norm[:8].upper()
            if not cls.is_valid(norm):
                return None
            return norm
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return bic.format(value)


class INN(IdentifierFormat):
    """Russian tax identification number."""

    NAME = "inn"
    TITLE = "INN"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return inn.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return inn.compact(inn.validate(value))
        except ValidationError:
            return None


class LEI(IdentifierFormat):
    """Legal Entity Identifier (ISO 17442)"""

    NAME = "lei"
    TITLE = "LEI"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return lei.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return lei.compact(lei.validate(value))
        except ValidationError:
            return None


class SSN(IdentifierFormat):
    """US Social Security Number"""

    NAME = "ssn"
    TITLE = "SSN"
    STRONG = False

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return ssn.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return ssn.compact(ssn.validate(value))
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return ssn.format(value)


class CPF(IdentifierFormat):
    """Cadastro de Pessoas Físicas, Brazilian national identifier"""

    NAME = "cpf"
    TITLE = "CPF"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return cpf.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return cpf.compact(cpf.validate(value))
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return cpf.format(value)


class CNPJ(IdentifierFormat):
    """Cadastro Nacional de Pessoas Jurídicas, Brazilian national companies identifier"""

    NAME = "cnpj"
    TITLE = "CNPJ"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return cnpj.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return cnpj.compact(cnpj.validate(value))
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return cnpj.format(value)


class USCC(IdentifierFormat):
    """Unified Social Credit Identifier, a Chinese national identifier"""

    NAME = "uscc"
    TITLE = "USCC"
    STRONG = True

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return uscc.is_valid(value)

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        try:
            return uscc.compact(uscc.validate(value))
        except ValidationError:
            return None

    @classmethod
    def format(cls, value: str) -> str:
        return uscc.format(value)
