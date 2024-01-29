from typing import Dict, List, Type
from typing_extensions import TypedDict

from rigour.ids.wikidata import WikidataQID
from rigour.ids.stdnum_ import IMO, ISIN, IBAN, FIGI, BIC, INN, LEI
from rigour.ids.stdnum_ import CPF, CNPJ
from rigour.ids.ogrn import OGRN
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
    "lei": LEI,
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
    "get_identifier_format",
    "get_identifier_formats",
    "get_identifier_format_names",
]
