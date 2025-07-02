import logging
from functools import cache
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from rigour.text.dictionary import Scanner, Normalizer
from rigour.names import Symbol, Name
from rigour.names import load_person_names_mapping
from rigour.names.tag import NameTypeTag, NamePartTag, GIVEN_NAME_TAGS

log = logging.getLogger(__name__)


class Tagger(Scanner):
    """A class to manage a dictionary of words and their aliases. This is used to perform
    replacement on those aliases or the word itself in a text.
    """

    def __init__(
        self,
        mapping: Dict[str, List[Symbol]],
    ) -> None:
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


def _common_symbols(normalizer: Normalizer) -> Dict[str, List[Symbol]]:
    """Get the common symbols for names."""
    from rigour.data.names.data import ORDINALS

    mapping: Dict[str, List[Symbol]] = defaultdict(list)
    for key, values in ORDINALS.items():
        sym = Symbol(Symbol.Category.ORDINAL, key)
        for value in values:
            nvalue = normalizer(value)
            if nvalue is None:
                continue
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)
    return mapping


@cache
def _get_org_tagger(normalizer: Normalizer) -> Tagger:
    """Get the organization name tagger."""
    from rigour.data.names.data import ORG_SYMBOLS
    from rigour.data.names.org_types import ORG_TYPES

    log.info("Loading org type/symbol tagger...")

    mapping = _common_symbols(normalizer)
    for key, values in ORG_SYMBOLS.items():
        sym = Symbol(Symbol.Category.SYMBOL, key.upper())
        nkey = normalizer(key)
        if nkey is not None:
            mapping[nkey].append(sym)
        for value in values:
            nvalue = normalizer(value)
            if nvalue is None:
                continue
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    for org_type in ORG_TYPES:
        class_sym: Optional[Symbol] = None
        generic = org_type.get("generic")
        if generic is None:
            continue
        class_sym = Symbol(Symbol.Category.ORG_CLASS, generic)
        display = org_type.get("display")
        if display is not None:
            display_norm = normalizer(display)
            if display_norm is not None:
                mapping[display_norm].append(class_sym)
        compare = org_type.get("compare", display)
        if compare is not None:
            compare_norm = normalizer(compare)
            if compare_norm is not None:
                mapping[compare_norm].append(class_sym)
        if compare is None:
            for alias in org_type.get("aliases", []):
                nalias = normalizer(alias)
                if nalias is None:
                    continue
                if class_sym not in mapping.get(nalias, []):
                    mapping[nalias].append(class_sym)

    log.info("Loaded organization tagger (%s terms).", len(mapping))
    return Tagger(mapping)


def _infer_part_tags(name: Name) -> Name:
    """Infer the tags of the name parts based on the name type."""
    for span in name.spans:
        if span.symbol.category == Symbol.Category.ORG_CLASS:
            if name.tag == NameTypeTag.ENT:
                # If an untyped entity name contains an organization type, we can tag
                # it as an organization.
                name.tag = NameTypeTag.ORG
            # If a name part is an organization class or type, we can tag it as legal.
            for part in span.parts:
                if part.tag == NamePartTag.ANY:
                    part.tag = NamePartTag.LEGAL
        if span.symbol.category == Symbol.Category.ORDINAL:
            if len(span.parts) == 1 and span.parts[0].tag == NamePartTag.ANY:
                # If an ordinal symbol is present and the part is not tagged, we can
                # tag it as numeric.
                span.parts[0].tag = NamePartTag.NUM
    for part in name.parts:
        if part.form.isnumeric() and part.tag == NamePartTag.ANY:
            # If a name part is numeric, we can tag it as numeric.
            part.tag = NamePartTag.NUM
    return name


def tag_org_name(name: Name, normalizer: Normalizer) -> Name:
    """Tag the name with the organization type and symbol tags."""
    tagger = _get_org_tagger(normalizer)
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)
    return _infer_part_tags(name)


@cache
def _get_person_tagger(normalizer: Normalizer) -> Tagger:
    """Get the person name tagger."""
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
    return Tagger(mapping)


def tag_person_name(
    name: Name, normalizer: Normalizer, any_initials: bool = False
) -> Name:
    """Tag a person's name with the person name part and other symbol tags."""
    # tag given name abbreviations. this is meant to handle a case where the person's
    # first or middle name is an abbreviation, e.g. "J. Smith" or "John Q. Smith"
    for part in name.parts:
        if not part.is_modern_alphabet:
            continue
        sym = Symbol(Symbol.Category.INITIAL, part.comparable[0])
        if any_initials and len(part.form) == 1:
            name.apply_part(part, sym)
        elif part.tag in GIVEN_NAME_TAGS:
            name.apply_part(part, sym)

    # tag the name with person symbols
    tagger = _get_person_tagger(normalizer)
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)

    return _infer_part_tags(name)
