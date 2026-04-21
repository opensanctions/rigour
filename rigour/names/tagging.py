"""Tag a :class:`Name` with symbol matches (org types, ordinals,
person names, locations, etc.).

Rust-backed via `rigour._core.tag_{org,person}_matches`. This module
is the thin Python wrapper that:

1. Normalises the name form through the Rust AC automaton to collect
   `(phrase, Symbol)` matches.
2. Applies each match to the `Name` via `Name.apply_phrase` (Python-
   side; `Name` is still Python-owned at this point in the port).
3. Runs :func:`_infer_part_tags` to promote `UNSET` parts to
   `NUM`/`STOP`/`LEGAL` based on the collected symbols.

The tagger build — iterating YAML-sourced data, running the per-
alias normaliser, assembling the AC automaton — lives entirely in
Rust (`rust/src/names/tagger.rs`) with a flag-keyed cache.
`ahocorasick-rs` is no longer needed.

See :mod:`rigour.text.normalize` for the `normalize_flags` / `cleanup`
vocabulary.
"""

from typing import Set

from rigour._core import tag_org_matches, tag_person_matches
from rigour.names import Name, Symbol
from rigour.names.part import NamePart
from rigour.names.tag import INITIAL_TAGS, NamePartTag, NameTypeTag
from rigour.names.tokenize import normalize_name
from rigour.text.normalize import Normalize
from rigour.text.stopwords import is_stopword

__all__ = ["tag_org_name", "tag_person_name"]

# Default flags for tagger reference-data normalisation. Mirrors the
# shape of `Name.norm_form` on the haystack side —
# `' '.join(tokenize_name(casefold(original)))` — as a single flag
# composition. The `NAME` flag runs `tokenize_name + ' '.join` as the
# final pipeline step, subsuming both SQUASH_SPACES and the Unicode-
# category handling / skip-char deletion that the tagger used to do
# in a hardcoded post-pass. No Cleanup is accepted: tokenize_name
# already handles categories, and `Cleanup.Strong` would drop chars
# the haystack keeps (CJK Lm, Mc), breaking matches.
_DEFAULT_FLAGS = Normalize.CASEFOLD | Normalize.NAME


def _infer_part_tags(name: Name, numerics: bool = True) -> Name:
    """Promote `UNSET` name parts based on collected symbols.

    Post-pass run after every tagger call:

    * A part inside an `ORG_CLASS`-categorised span flips to
      `NamePartTag.LEGAL`; a long such span also upgrades the whole
      name's tag from `ENT` to `ORG`.
    * A numeric-looking UNSET part flips to `NamePartTag.NUM` and —
      when `numerics=True` — gains a `NUMERIC` symbol if it doesn't
      already have one from an ordinal/cardinal AC match.
    * An UNSET part that's a stopword flips to `NamePartTag.STOP`.

    Args:
        name: The `Name` to mutate in place.
        numerics: If `True` (default), emit `Symbol(NUMERIC, value)`
            for numeric-looking parts the AC tagger didn't already
            cover. If `False`, still tag structure (`NamePartTag.NUM`)
            but skip the symbol emission — useful for callers that
            don't consume numeric-symbol overlap for scoring.
    """
    known_numerics: Set[NamePart] = set()
    for span in name.spans:
        if span.symbol.category == Symbol.Category.ORG_CLASS:
            if name.tag == NameTypeTag.ENT and len(span) > 2:
                name.tag = NameTypeTag.ORG
            for part in span.parts:
                if part.tag == NamePartTag.UNSET:
                    part.tag = NamePartTag.LEGAL
        if span.symbol.category == Symbol.Category.NUMERIC:
            for part in span.parts:
                known_numerics.add(part)
    for part in name.parts:
        if part.tag == NamePartTag.UNSET:
            if part.numeric:
                part.tag = NamePartTag.NUM
                if numerics and part not in known_numerics:
                    value = part.integer
                    if value is not None:
                        sym = Symbol(Symbol.Category.NUMERIC, value)
                        name.apply_part(part, sym)
                    known_numerics.add(part)
            elif is_stopword(part.form, normalizer=normalize_name):
                part.tag = NamePartTag.STOP
    return name


def tag_org_name(
    name: Name,
    normalize_flags: Normalize = _DEFAULT_FLAGS,
    numerics: bool = True,
) -> Name:
    """Tag an organisation Name with org-class + location + ordinal
    symbols.

    Args:
        name: The `Name` to tag. Mutated in place (spans added,
            parts' tags promoted); also returned for chaining.
        normalize_flags: `Normalize` flags used on the tagger's internal
            alias set. Default is `CASEFOLD | NAME` — the `NAME` flag
            runs `tokenize_name + join` as the final pipeline step,
            producing the same shape as `Name.norm_form` on the
            haystack side.
        numerics: Forwarded to :func:`_infer_part_tags`. Default
            `True` preserves historical behaviour (emit NUMERIC
            symbols on arbitrary numeric parts). Pass `False` to
            tag structure only.

    Returns:
        The mutated `name`.
    """
    matches = tag_org_matches(name.norm_form, int(normalize_flags))
    for phrase, symbol in matches:
        name.apply_phrase(phrase, symbol)
    return _infer_part_tags(name, numerics=numerics)


def tag_person_name(
    name: Name,
    normalize_flags: Normalize = _DEFAULT_FLAGS,
    infer_initials: bool = False,
    numerics: bool = True,
) -> Name:
    """Tag a person Name with name-part + nick + ordinal + initial
    symbols.

    Args:
        name: The `Name` to tag. Mutated in place.
        normalize_flags: `Normalize` flags. Same role as in
            :func:`tag_org_name`.
        infer_initials: If True, treat every single-character latin
            name part as an INITIAL symbol (used on the matching query
            side where "J Smith" arrives without a GIVEN/MIDDLE tag).
            When False, only parts already tagged as GIVEN/MIDDLE pick
            up INITIAL symbols.
        numerics: Forwarded to :func:`_infer_part_tags`.

    Returns:
        The mutated `name`.
    """
    # INITIAL preamble: tag single-letter / given-or-middle-tagged
    # parts with INITIAL symbols. Pure Name-internal logic; doesn't
    # go through the AC automaton.
    for part in name.parts:
        if not part.latinize:
            continue
        sym = Symbol(Symbol.Category.INITIAL, part.comparable[0])
        if infer_initials and len(part.form) == 1:
            name.apply_part(part, sym)
        elif part.tag in INITIAL_TAGS:
            name.apply_part(part, sym)

    matches = tag_person_matches(name.norm_form, int(normalize_flags))
    for phrase, symbol in matches:
        name.apply_phrase(phrase, symbol)

    return _infer_part_tags(name, numerics=numerics)
