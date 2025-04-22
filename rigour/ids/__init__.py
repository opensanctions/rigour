"""
Handling of person, organisation and object identifiers. This module contains a collection of validation
and formatting tools for identifiers. The `IdentifierFormat` class is the base class for all identifier formats,
and it provides a common interface for validation and formatting.

Currently, identifers can be accessed using short aliases, such as "imo" or "isin". In the future, we will
need to introduce a proper, structured identification scheme for identifiers, with qualifiers for country
(e.g. `ru:nalog:inn`, `us:sam:uei`).
"""

from functools import cache
from typing import Dict, List, Type
from typing_extensions import TypedDict

from rigour.ids.wikidata import WikidataQID
from rigour.ids.stdnum_ import ISIN, IBAN, FIGI, BIC, INN, LEI
from rigour.ids.stdnum_ import CPF, CNPJ, SSN
from rigour.ids.ogrn import OGRN
from rigour.ids.npi import NPI
from rigour.ids.uei import UEI
from rigour.ids.imo import IMO
from rigour.ids.strict import StrictFormat
from rigour.ids.common import IdentifierFormat

FORMATS: Dict[str, Type[IdentifierFormat]] = {
    "wikidata": WikidataQID,
    "qid": WikidataQID,
    "ogrn": OGRN,
    "imo": IMO,
    "isin": ISIN,
    "iban": IBAN,
    "figi": FIGI,
    "openfigi": FIGI,
    "bic": BIC,
    "swift": BIC,
    "inn": INN,
    "npi": NPI,
    "lei": LEI,
    "uei": UEI,
    "ssn": SSN,
    "cpf": CPF,
    "cnpj": CNPJ,
    "generic": IdentifierFormat,
    "null": IdentifierFormat,
    "strict": StrictFormat,
}


class FormatSpec(TypedDict):
    """An identifier format specification."""

    title: str
    names: List[str]
    description: str


def get_identifier_format(name: str) -> Type[IdentifierFormat]:
    """Get the identifier type class for the given format name."""
    return FORMATS[name]


def get_identifier_format_names() -> List[str]:
    """Get a list of all identifier type names."""
    return list(FORMATS.keys())


def get_identifier_formats() -> List[FormatSpec]:
    """Get a list of all identifier formats."""
    formats: List[FormatSpec] = []
    for type_ in set(FORMATS.values()):
        names = [name for name, cls in FORMATS.items() if cls == type_]
        fmt: FormatSpec = {
            "names": names,
            "title": type_.TITLE,
            "description": type_.__doc__ or "",
        }
        formats.append(fmt)
    return sorted(formats, key=lambda f: f["title"])


@cache
def get_strong_format_names() -> List[str]:
    """Get a list of all strong identifier type names."""
    return [name for name, cls in FORMATS.items() if cls.STRONG]


__all__ = [
    "IdentifierFormat",
    "StrictFormat",
    "WikidataQID",
    "OGRN",
    "IMO",
    "ISIN",
    "IBAN",
    "FIGI",
    "BIC",
    "INN",
    "LEI",
    "NPI",
    "UEI",
    "SSN",
    "CPF",
    "CPNJ",
    "get_identifier_format",
    "get_identifier_formats",
    "get_identifier_format_names",
]
