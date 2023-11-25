from rigour.ids.wikidata import WikidataQID
from rigour.ids.stdnum_ import IMO, ISIN, IBAN, FIGI, BIC, INN, LEI
from rigour.ids.ogrn import OGRN
from rigour.ids.common import IdentifierType

FORMATS = {
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
}


__all__ = [
    "IdentifierType",
    "WikidataQID",
    "OGRN",
    "IMO",
    "ISIN",
    "IBAN",
    "FIGI",
    "BIC",
    "INN",
    "LEI",
]
