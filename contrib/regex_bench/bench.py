import logging
from typing import Dict, List, Optional, Tuple, Type

from rigour.names.person import load_person_names_mapping
from rigour.names.symbol import Symbol
from rigour.names.tagging import _common_symbols
from rigour.text.dictionary import Normalizer, Scanner as REScanner
from rigour.names.tagging import Tagger as RETagger
from rigour.names import prenormalize_name

log = logging.getLogger(__name__)


def load_scanner_class(name: str) -> Type[REScanner]:
    """Load a scanner class by name."""
    if name == "re2":
        from impl.dictionary_re2 import Scanner
    elif name == "re":
        Scanner = REScanner
    else:
        raise ValueError(f"Unknown scanner type: {name}")
    return Scanner


def load_tagger_class(Scanner: Type[REScanner]) -> Type[RETagger]:
    class Tagger(Scanner):
        """A class to manage a dictionary of words and their aliases. This is used to perform
        replacement on those aliases or the word itself in a text.
        """
        def __init__(self, mapping: Dict[str, List[Symbol]]) -> None:
            forms = list(mapping.keys())
            super().__init__(forms, ignore_case=False)
            self.mapping = mapping

        def __call__(self, text: Optional[str]) -> List[Tuple[str, Symbol]]:
            """Apply the tagger on a piece of pre-normalized text."""
            if text is None:
                return []
            symbols: List[Tuple[str, Symbol]] = []
            for match in self.pattern.finditer(text):
                value = match.group(1)
                for symbol in self.mapping.get(value, []):
                    symbols.append((value, symbol))

            for token in text.split(" "):
                if token in self.mapping:
                    for symbol in self.mapping[token]:
                        if (token, symbol) not in symbols:
                            symbols.append((token, symbol))
            return symbols

    return Tagger


def _get_person_name_mapping(normalizer: Normalizer) -> Dict[str, List[Symbol]]:
    from rigour.data.names.data import PERSON_SYMBOLS

    mapping = _common_symbols(normalizer)
    for key, values in PERSON_SYMBOLS.items():
        sym = Symbol(Symbol.Category.SYMBOL, key.upper())
        nkey = normalizer(key)
        if nkey is not None:
            mapping[nkey].append(Symbol(Symbol.Category.SYMBOL, key))
        for value in values:
            nvalue = normalizer(value)
            if nvalue is None:
                continue
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    name_mapping = load_person_names_mapping(normalizer=normalizer)
    for name, qids in name_mapping.items():
        for qid in qids:
            sym = Symbol(Symbol.Category.NAME, int(qid[1:]))
            mapping[name].append(sym)

    log.info("Loaded person tagger (%s terms).", len(mapping))
    return mapping


def normalizer(text: Optional[str]) -> Optional[str]:
    """Normalize a name by removing extra spaces and converting to lowercase."""
    if text is None:
        return None
    text = prenormalize_name(text)
    if not text:
        return None
    return " ".join(text.split())


if __name__ == "__main__":
    Scanner = load_scanner_class("re2")
    Tagger = load_tagger_class(Scanner)
    tag = Tagger(_get_person_name_mapping(normalizer))
    print(tag(normalizer("John Doe")))
