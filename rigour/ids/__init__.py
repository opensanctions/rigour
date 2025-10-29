"""
Handling of person, organisation and object identifiers. This module contains a collection of validation
and formatting tools for identifiers. The `IdentifierFormat` class is the base class for all identifier formats,
and it provides a common interface for validation and formatting.

Currently, identifers can be accessed using short aliases, such as "imo" or "isin". In the future, we will
need to introduce a proper, structured identification scheme for identifiers, with qualifiers for country
(e.g. `ru:nalog:inn`, `us:sam:uei`).
"""

from functools import cache
from typing import List, Optional, Tuple, Type
from typing_extensions import TypedDict

from rigour.ids.wikidata import WikidataQID
from rigour.ids.stdnum_ import ISIN, IBAN, FIGI, BIC, INN, LEI, USCC
from rigour.ids.stdnum_ import CPF, CNPJ, SSN
from rigour.ids.ogrn import OGRN
from rigour.ids.npi import NPI
from rigour.ids.uei import UEI
from rigour.ids.imo import IMO
from rigour.ids.strict import StrictFormat
from rigour.ids.common import IdentifierFormat

FormatType = Type[IdentifierFormat]

_FORMATS: Tuple[FormatType, ...] = (
    WikidataQID,
    OGRN,
    IMO,
    ISIN,
    IBAN,
    FIGI,
    BIC,
    INN,
    NPI,
    LEI,
    UEI,
    SSN,
    CPF,
    CNPJ,
    USCC,
    IdentifierFormat,
    StrictFormat,
)

FORMAT_ALIASES = {
    "qid": WikidataQID.NAME,
    "swift": BIC.NAME,
    "openfigi": FIGI.NAME,
    "null": IdentifierFormat.NAME,
}


class FormatSpec(TypedDict):
    """An identifier format specification."""

    name: str
    title: str
    description: str
    strong: bool


@cache
def get_identifier_format(name: str) -> Optional[FormatType]:
    """Get the identifier type class for the given format name."""
    name = FORMAT_ALIASES.get(name, name)
    for fmt in _FORMATS:
        if fmt.NAME == name:
            return fmt
    return None


def get_identifier_format_names() -> List[str]:
    """Get a list of all identifier type names."""
    return [fmt.NAME for fmt in _FORMATS]


def get_identifier_formats() -> List[FormatSpec]:
    """Get a list of all identifier formats."""
    formats: List[FormatSpec] = []
    for type_ in _FORMATS:
        name = type_.NAME
        fmt: FormatSpec = {
            "name": name,
            "title": type_.TITLE,
            "description": type_.__doc__ or "",
            "strong": type_.STRONG,
        }
        formats.append(fmt)
    return sorted(formats, key=lambda f: f["title"])


@cache
def get_strong_format_names() -> List[str]:
    """Get a list of all strong identifier type names."""
    return [fmt.NAME for fmt in _FORMATS if fmt.STRONG]


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
    "CNPJ",
    "USCC",
    "get_identifier_format",
    "get_identifier_formats",
    "get_identifier_format_names",
]
