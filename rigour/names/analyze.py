"""End-to-end name analysis: raw strings → tagged [Name][rigour.names.Name] objects.

`analyze_names` is the unified entry point that downstream consumers
(followthemoney's `entity_names`, in turn used by nomenklatura and
yente) call once per entity to get matchable `Name` objects.

Rust-backed via `rigour._core.analyze_names` — one FFI crossing per
call, regardless of how many names / part_tags the entity has. The
single-call pipeline runs: prefix strip → prenormalize → org-type
replacement (for ORG/ENT) → `Name` + `NamePart` construction → part
tagging via `Name.tag_text` → tagger match-and-apply → `NUMERIC` /
`STOP` / `LEGAL` inference → optional `consolidate_names`.

## Part-tag value shape

`part_tags` values can be **multi-token strings**. A value like
``"Jean Claude"`` in ``part_tags[NamePartTag.GIVEN]`` for the name
``"Jean Claude Juncker"`` will tag both the ``"jean"`` and
``"claude"`` parts as `GIVEN` — the underlying `Name.tag_text`
tokenises the value and walks the name parts looking for the token
sequence. The tokens of the value don't need to be adjacent in the
name, just present in order.
"""

from typing import Mapping, Optional, Sequence, Set

from rigour._core import analyze_names as _analyze_names
from rigour.names.name import Name
from rigour.names.tag import NamePartTag, NameTypeTag

__all__ = ["analyze_names"]


def analyze_names(
    type_tag: NameTypeTag,
    names: Sequence[str],
    part_tags: Optional[Mapping[NamePartTag, Sequence[str]]] = None,
    *,
    infer_initials: bool = False,
    symbols: bool = True,
    phonetics: bool = True,
    numerics: bool = True,
    consolidate: bool = True,
) -> Set[Name]:
    """Build a set of tagged [Name][rigour.names.Name] objects from raw strings.

    Args:
        type_tag: The [NameTypeTag][rigour.names.NameTypeTag] for
            every name in this batch. Drives which prefix/org-type/
            tagger passes run: `PER` → person prefix strip + person
            tagger; `ORG`/`ENT` → org-type replacement + org prefix
            strip + org tagger; `OBJ`/`UNK` → no tagging, just
            construction.
        names: Raw name strings as harvested from the source entity.
            Empty strings and inputs that normalise to empty are
            dropped. Duplicates (after prenormalisation) are de-duplicated.
        part_tags: Pre-classified part annotations, typically produced
            by an adapter that reads structured name-part properties
            off the source entity (e.g. firstName → `GIVEN`,
            lastName → `FAMILY`). Each value is applied to every
            constructed `Name` via `Name.tag_text`. Values can be
            multi-token strings — see the module docstring. Defaults
            to an empty mapping.
        infer_initials: When `True`, every single-character latin name
            part is tagged with an `INITIAL` symbol — useful on a
            free-text query side where `"J Smith"` arrives without
            a label on `"J"`. When `False` (default), only parts
            already tagged as `GIVEN` / `MIDDLE` pick up `INITIAL`
            symbols. Default `False` because initials are a
            query-side concept; the indexer and the candidate side
            of a matcher pass `False`, so the leaner default suits
            the common call. Ignored for non-person names. No-op
            when `symbols=False`.
        symbols: Master switch for symbol emission. When `True`
            (default), the INITIAL preamble, the AC tagger's
            match-and-apply pass, and NUMERIC-symbol emission all
            run. When `False`, no symbols are attached to the
            returned names — `name.symbols` is empty and
            `name.spans` stays empty. NamePartTag labelling
            (including the `NUM` / `STOP` / `LEGAL` promotions in
            the inference pass) still fires, and `part_tags` values
            are still applied via `Name.tag_text`. Useful for
            callers that only need tokens + part tags and don't
            match on symbol overlap; skipping the AC tagger is the
            main performance saving.
        phonetics: When `True` (default), each `NamePart.metaphone`
            is populated at construction; when `False`, the field
            stays `None` and the phonetics crate isn't called.
            Consumers that feed `part.metaphone` into downstream
            fields (e.g. yente's `name_phonemes` ES field) keep the
            default; callers that never read the property can save
            the per-part metaphone call.
        numerics: When `True` (default), numeric-looking name parts
            that the AC tagger's ordinal list didn't cover get a
            `Symbol(NUMERIC, int_value)` applied. When `False`, parts
            still get `NamePartTag.NUM` (cheap structural info) but
            no NUMERIC symbol is emitted. Callers that don't use
            numeric-symbol overlap for scoring can save the symbol
            allocation.
        consolidate: When `True` (default), the returned set has
            [Name.consolidate_names][rigour.names.Name.consolidate_names]
            applied — short names that are substrings of longer names
            in the same set are dropped. **Indexers should pass
            `consolidate=False`** to preserve partial-name recall
            (e.g. letting `"John Smith"` match `"John K Smith"` from
            the other side).

    Returns:
        A set of tagged `Name` objects, de-duplicated by normalised
        form. Empty if every input normalised to an empty string.
    """
    tag_dict: dict[NamePartTag, list[str]] | None
    if part_tags is None:
        tag_dict = None
    else:
        tag_dict = {tag: list(values) for tag, values in part_tags.items()}
    return _analyze_names(
        type_tag,
        list(names),
        tag_dict,
        infer_initials=infer_initials,
        symbols=symbols,
        phonetics=phonetics,
        numerics=numerics,
        consolidate=consolidate,
    )
