from typing import Optional
from stdnum import imo, isin, iban, figi, bic, lei  # type: ignore
from stdnum.ru import inn  # type: ignore
from stdnum.br import cpf, cnpj  # type: ignore

from rigour.ids.common import StdnumFormat


class IMO(StdnumFormat):
    """An IMO number for a ship."""

    TITLE = "IMO"

    impl = imo


class ISIN(StdnumFormat):
    """An ISIN number for a security."""

    TITLE = "ISIN"

    impl = isin

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class IBAN(StdnumFormat):
    """An IBAN number for a bank account."""

    TITLE = "IBAN"

    impl = iban


class FIGI(StdnumFormat):
    """A FIGI number for a security, as managed by OpenFIGI."""

    TITLE = "FIGI"

    impl = figi

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class BIC(StdnumFormat):
    """BIC (ISO 9362 Business identifier codes)."""

    TITLE = "BIC"

    impl = bic

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        norm = super().normalize(value)
        if norm is not None:
            norm = norm[:8]
        return norm


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

    impl = lei

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()


class CPF(StdnumFormat):
    """Cadastro de Pessoas Físicas, Brazilian national identifier"""

    TITLE = "CPF"

    impl = cpf

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()

    @classmethod
    def normalize(cls, value: str) -> str:
        """Remove punctuation from a CPF number.
        If it is already clean, it will return it as is.
        The CPF number is a Brazilian tax identification number for individuals
        that is formatted with punctuation (XXX.XXX.XXX-XX) to make it easier to
        read. However, when saving the CPF number in the database, it's common
        to remove the punctuation.
        Args:
            cpf: The CPF number to be cleaned.
        Returns:
            The cleaned CPF number.
        """

        # Remove formatting characters
        return value.replace(".", "").replace("-", "")

class CNPJ(StdnumFormat):
    """Cadastro Nacional de Pessoas Jurídicas, Brazilian companies national identifier"""

    TITLE = "CNPJ"

    impl = cnpj

    @classmethod
    def format(cls, value: str) -> str:
        return value.upper()

    @classmethod
    def normalize(cls, value: str) -> str:
        """Remove punctuation from a CNPJ number.
        If it is already clean, it will return it as is.
        The CNPJ number is a Brazilian tax identification number for companies
        that is typically formatted with punctuation (XX.XXX.XXX/XXXX-XX) to make
        it easier to read. However, when saving the CNPJ number in a database, 
        it's common to remove the punctuation.
        Args:
            cnpj: The CNPJ number to be cleaned.
        Returns:
            The cleaned CNPJ number or an empty string if the CNPJ is not valid.
        """

        # Remove formatting characters
        return cnpj.replace(".", "").replace("/", "").replace("-", "")