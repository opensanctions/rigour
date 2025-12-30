import re
import sys
import logging
from functools import cache
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from rigour.data import read_jsonl
from rigour.text.dictionary import Normalizer
from rigour.names import Symbol, Name
from rigour.names import load_person_names
from rigour.names.check import is_stopword
from rigour.names.part import NamePart
from rigour.names.tag import NameTypeTag, NamePartTag, INTITIAL_TAGS
from rigour.territories.territory import TERRITORIES_FILE
from rigour.util import resource_lock, unload_module

import ahocorasick_rs

log = logging.getLogger(__name__)

REGEX_TOKENS = re.compile(r"(?<!\w)([\w\.-]+)(?!\w)")


def word_boundary_matches(
    text: str, matches: List[Tuple[int, int, int]]
) -> List[Tuple[int, int, int]]:
    """Keep only matches starting and ending on some token boundary in the text"""
    # Find boundaries of tokens in the text
    boundaries = set()
    for word_match in REGEX_TOKENS.finditer(text):
        boundaries.add(word_match.start())
        boundaries.add(word_match.end())

    token_matches: List[Tuple[int, int, int]] = []
    for pattern_index, start, end in matches:
        # Skip any matches that aren't along token boundaries
        if start not in boundaries or end not in boundaries:
            continue
        token_matches.append((pattern_index, start, end))
    return token_matches


class Tagger:
    """A class to manage a dictionary of words and the symbols they match."""

    def __init__(self, mapping: Dict[str, Set[Symbol]]) -> None:
        self._symbols: List[Tuple[Symbol, ...]] = []
        """Indexed list of symbols for each pattern."""
        forms = []
        for k, v in mapping.items():
            # Skip empty key
            if k is None or k == "":
                continue
            self._symbols.append(tuple(v))
            forms.append(k)
        self.automaton = ahocorasick_rs.AhoCorasick(forms)

    def __call__(self, text: str) -> List[Tuple[str, Symbol]]:
        """Apply the tagger on a piece of pre-normalized text."""
        results: List[Tuple[str, Symbol]] = []
        matches = self.automaton.find_matches_as_indexes(text, overlapping=True)
        matches = word_boundary_matches(text, matches)
        for pattern_index, start, end in sorted(matches, key=lambda x: x[0]):
            match_string = text[start:end]
            for symbol in self._symbols[pattern_index]:
                results.append((match_string, symbol))

        return results


def _common_symbols(normalizer: Normalizer) -> Dict[str, Set[Symbol]]:
    """Get the common symbols for names."""
    from rigour.data.text.ordinals import ORDINALS

    mapping: Dict[str, Set[Symbol]] = defaultdict(set)
    for key, values in ORDINALS.items():
        sym = Symbol(Symbol.Category.NUMERIC, key)
        for value in values:
            nvalue = normalizer(value)
            if nvalue is not None:
                mapping[nvalue].add(sym)

    unload_module("rigour.data.text.ordinals")
    return mapping


@cache
def _get_org_tagger(normalizer: Normalizer) -> Tagger:
    """Get the organization name tagger."""
    from rigour.data.names.data import ORG_SYMBOLS, ORG_DOMAINS
    from rigour.data.names.org_types import ORG_TYPES

    log.info("Loading org type/symbol tagger...")

    mapping = _common_symbols(normalizer)
    for key, values in ORG_SYMBOLS.items():
        sym = Symbol(Symbol.Category.SYMBOL, key.upper())
        for value in values:
            nvalue = normalizer(value)
            if nvalue is not None:
                mapping[nvalue].add(sym)

    for key, values in ORG_DOMAINS.items():
        sym = Symbol(Symbol.Category.DOMAIN, key.upper())
        for value in values:
            nvalue = normalizer(value)
            if nvalue is not None:
                mapping[nvalue].add(sym)

    for data in read_jsonl(TERRITORIES_FILE):
        sym = Symbol(Symbol.Category.LOCATION, sys.intern(data["code"]))
        names: List[str] = data.get("names_strong", [])
        names.append(data["name"])
        names.append(data["full_name"])
        for name in names:
            nname = normalizer(name)
            if nname is not None and len(nname):  # pragma: no cover
                mapping[nname].add(sym)

    symbols: Dict[str, Symbol] = {}
    for org_type in ORG_TYPES:
        generic = org_type.get("generic")
        if generic is None:
            continue
        if generic not in symbols:
            symbols[generic] = Symbol(Symbol.Category.ORG_CLASS, sys.intern(generic))
        class_sym = symbols[generic]
        display = org_type.get("display")
        if display is not None:
            dn = normalizer(display)
            if dn is not None:  # pragma: no cover
                mapping[dn].add(class_sym)
        compare = org_type.get("compare", display)
        if compare is not None:
            cn = normalizer(compare)
            if cn is not None:  # pragma: no cover
                mapping[cn].add(class_sym)
        if compare is None:
            for alias in org_type.get("aliases", []):
                nalias = normalizer(alias)
                if nalias is not None:  # pragma: no cover
                    mapping[nalias].add(class_sym)

    unload_module("rigour.data.names.data")
    unload_module("rigour.data.names.org_types")
    log.info("Loaded organization tagger (%s terms).", len(mapping))
    return Tagger(mapping)


def _infer_part_tags(name: Name) -> Name:
    """Infer the tags of the name parts based on the name type."""
    numerics: Set[NamePart] = set()
    for span in name.spans:
        if span.symbol.category == Symbol.Category.ORG_CLASS:
            if name.tag == NameTypeTag.ENT and len(span) > 2:
                # If an untyped entity name contains an organization type, we can tag
                # it as an organization.
                name.tag = NameTypeTag.ORG
            # If a name part is an organization class or type, we can tag it as legal.
            for part in span.parts:
                if part.tag == NamePartTag.UNSET:
                    part.tag = NamePartTag.LEGAL
        if span.symbol.category == Symbol.Category.NUMERIC:
            for part in span.parts:
                numerics.add(part)
        #     if len(span.parts) == 1 and span.parts[0].tag == NamePartTag.UNSET:
        #         # If a numeric symbol is present and the part is not tagged, we can
        #         # tag it as numeric.
        #         span.parts[0].tag = NamePartTag.NUM
    for part in name.parts:
        if part.tag == NamePartTag.UNSET:
            if part.numeric:
                # If a name part is numeric, we can tag it as numeric.
                part.tag = NamePartTag.NUM
                # And apply a symbol, if missing:
                if part not in numerics:
                    value = part.integer
                    if value is not None:
                        sym = Symbol(Symbol.Category.NUMERIC, value)
                        name.apply_part(part, sym)
                    numerics.add(part)
            elif is_stopword(part.form):
                # If a name part is a stop word, we can tag it as a stop word.
                part.tag = NamePartTag.STOP
    return name


def tag_org_name(name: Name, normalizer: Normalizer) -> Name:
    """Tag the name with the organization type and symbol tags."""
    with resource_lock:
        tagger = _get_org_tagger(normalizer)
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)
    return _infer_part_tags(name)


@cache
def _get_person_tagger(normalizer: Normalizer) -> Tagger:
    """Get the person name tagger."""
    from rigour.data.names.data import PERSON_SYMBOLS, PERSON_NAME_PARTS, PERSON_NICK

    mapping = _common_symbols(normalizer)
    for key, values in PERSON_SYMBOLS.items():
        sym = Symbol(Symbol.Category.SYMBOL, key.upper())
        for value in values:
            nvalue = normalizer(value)
            if nvalue is not None:
                mapping[nvalue].add(sym)

    for key, values in PERSON_NAME_PARTS.items():
        sym = Symbol(Symbol.Category.NAME, key.upper())
        for value in values:
            nvalue = normalizer(value)
            if nvalue is not None:  # pragma: no cover
                mapping[nvalue].add(sym)

    for key, values in PERSON_NICK.items():
        sym = Symbol(Symbol.Category.NICK, key.upper())
        for value in values:
            nvalue = normalizer(value)
            if nvalue is not None:  # pragma: no cover
                mapping[nvalue].add(sym)

    for gid, aliases in load_person_names():
        sym = Symbol(Symbol.Category.NAME, int(gid[1:]))
        forms: Set[str] = set()
        for alias in aliases:
            norm_alias = normalizer(alias)
            if norm_alias is not None and len(norm_alias):
                forms.add(norm_alias)
        if len(forms) < 2:
            continue
        for form in forms:
            mapping[form].add(sym)

    unload_module("rigour.data.names.data")
    log.info("Loaded person tagger (%s terms).", len(mapping))
    return Tagger(mapping)


def tag_person_name(
    name: Name, normalizer: Normalizer, any_initials: bool = False
) -> Name:
    """Tag a person's name with the person name part and other symbol tags."""
    # tag given name abbreviations. this is meant to handle a case where the person's
    # first or middle name is an abbreviation, e.g. "J. Smith" or "John Q. Smith"
    for part in name.parts:
        if not part.latinize:
            continue
        sym = Symbol(Symbol.Category.INITIAL, part.comparable[0])
        if any_initials and len(part.form) == 1:
            name.apply_part(part, sym)
        elif part.tag in INTITIAL_TAGS:
            name.apply_part(part, sym)

    # tag the name with person symbols
    with resource_lock:
        tagger = _get_person_tagger(normalizer)
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)

    return _infer_part_tags(name)
