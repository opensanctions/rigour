"""End-to-end name analysis: raw strings → tagged [Name][rigour.names.Name] objects.

`analyze_names` is the unified entry point that downstream consumers
(followthemoney's `entity_names`, in turn used by nomenklatura and
yente) call once per entity to get matchable `Name` objects. It
composes the existing rigour primitives —
[prenormalize_name][rigour.names.tokenize.prenormalize_name],
[remove_person_prefixes][rigour.names.prefix.remove_person_prefixes],
[replace_org_types_compare][rigour.names.org_types.replace_org_types_compare],
[remove_org_prefixes][rigour.names.prefix.remove_org_prefixes],
[Name][rigour.names.Name] construction with part tagging via
[Name.tag_text][rigour.names.Name.tag_text],
[tag_org_name][rigour.names.tagging.tag_org_name] /
[tag_person_name][rigour.names.tagging.tag_person_name],
and optional [Name.consolidate_names][rigour.names.Name.consolidate_names]
— into a single call so callers cross the rigour boundary once
instead of per-primitive.

## Part-tag value shape

`part_tags` values can be **multi-token strings**. A value like
``"Jean Claude"`` in ``part_tags[NamePartTag.GIVEN]`` for the name
``"Jean Claude Juncker"`` will tag both the ``"jean"`` and
``"claude"`` parts as `GIVEN` — `Name.tag_text` tokenises the value
and walks the name parts looking for the token sequence. The tokens
of the value don't need to be adjacent in the name (see
`Name.tag_text` for the full matching rule), just present in order.
"""

from typing import Mapping, Optional, Sequence, Set

from rigour.names.name import Name
from rigour.names.org_types import replace_org_types_compare
from rigour.names.prefix import remove_org_prefixes, remove_person_prefixes
from rigour.names.tag import NamePartTag, NameTypeTag
from rigour.names.tagging import tag_org_name, tag_person_name
from rigour.names.tokenize import prenormalize_name

__all__ = ["analyze_names"]


def analyze_names(
    type_tag: NameTypeTag,
    names: Sequence[str],
    part_tags: Optional[Mapping[NamePartTag, Sequence[str]]] = None,
    *,
    infer_initials: bool = False,
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
        infer_initials: Passed through to
            [tag_person_name][rigour.names.tagging.tag_person_name].
            When `True`, every single-character latin name part is
            tagged with an `INITIAL` symbol — useful on a free-text
            query side where `"J Smith"` arrives without a label on
            `"J"`. When `False` (default), only parts already tagged
            as `GIVEN` / `MIDDLE` pick up `INITIAL` symbols. Default
            `False` because initials are a query-side concept; the
            indexer and the candidate side of a matcher pass `False`,
            so the leaner default suits the common call. Ignored for
            non-person names.
        phonetics: Accepted for API forward-compatibility with the
            future Rust port. In this Python shim it has **no runtime
            effect** — `NamePart.metaphone` is a computed property
            that always runs on access. Once the Rust port lands,
            `phonetics=False` will skip the metaphone computation at
            construction time; until then, the flag is inert.
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
    # `phonetics` is accepted but unused in this Python shim; see the
    # Args note above. Touch the name to keep linters quiet.
    _ = phonetics

    tag_map: Mapping[NamePartTag, Sequence[str]] = part_tags or {}
    seen: Set[str] = set()
    result: Set[Name] = set()
    for raw in names:
        if type_tag == NameTypeTag.PER:
            raw = remove_person_prefixes(raw)
        form = prenormalize_name(raw)
        if type_tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            form = replace_org_types_compare(form)
            form = remove_org_prefixes(form)
        if not form or form in seen:
            continue
        seen.add(form)
        name = Name(raw, form=form, tag=type_tag)
        for tag, values in tag_map.items():
            for value in values:
                name.tag_text(prenormalize_name(value), tag)
        if type_tag in (NameTypeTag.ORG, NameTypeTag.ENT):
            tag_org_name(name, numerics=numerics)
        elif type_tag == NameTypeTag.PER:
            tag_person_name(
                name, infer_initials=infer_initials, numerics=numerics
            )
        # OBJ / UNK: no tagger pass — Name just wraps raw + form + parts.
        result.add(name)
    if consolidate:
        return Name.consolidate_names(result)
    return result
