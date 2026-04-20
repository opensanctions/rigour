"""Organisation and company-types database.

Normalise and replace organisation types — such as company legal
forms — in an entity name. The objective is to standardise the
representation of these types and to facilitate name matching on
organisations and companies.

The resource data lives in
[org_types.yml](https://github.com/opensanctions/rigour/blob/main/resources/names/org_types.yml).
The database is originally based on three sources:

* A [Google Spreadsheet](https://docs.google.com/spreadsheets/d/1Cw2xQ3hcZOAgnnzejlY5Sv3OeMxKePTqcRhXQU8rCAw/edit?ts=5e7754cf#gid=0)
  created by OCCRP.
* ISO 20275: [Entity Legal Forms Code List](https://www.gleif.org/en/about-lei/code-lists/iso-20275-entity-legal-forms-code-list).
* Wikipedia's index of [types of business entity](https://en.wikipedia.org/wiki/Types_of_business_entity).

All four public functions take `normalize_flags` and `cleanup`
parameters that control how the YAML alias list is normalised at
match-table build time. The caller is expected to normalise runtime
input with the *same* flags before calling — see
[rigour.text.normalize][] for the canonical reference on flag
semantics and common compositions.

Implementation is Rust-backed via `rigour._core`: an Aho-Corasick
automaton with a Python-style `(?<!\\w)X(?!\\w)` boundary check,
compiled once per `(kind, flags, cleanup)` combination.
"""

from typing import List, Tuple

from rigour._core import (
    extract_org_types as _extract_org_types,
    remove_org_types as _remove_org_types,
    replace_org_types_compare as _replace_org_types_compare,
    replace_org_types_display as _replace_org_types_display,
)
from rigour.text.normalize import Cleanup, Normalize

__all__ = [
    "replace_org_types_compare",
    "replace_org_types_display",
    "remove_org_types",
    "extract_org_types",
]


def replace_org_types_compare(
    name: str,
    normalize_flags: Normalize = Normalize.CASEFOLD,
    cleanup: Cleanup = Cleanup.Noop,
    generic: bool = False,
) -> str:
    """Replace organisation types in a name with a heavily normalised form.

    Country-specific entity types (e.g. GmbH, Aktiengesellschaft, ООО) are
    rewritten into a simplified comparison form (e.g. ``gmbh``, ``ag``,
    ``ooo``) suitable for string-distance matching. The result is meant
    for comparison pipelines, not for presentation.

    Args:
        name: The text to be processed. Assumed to already be normalised
            with the same `normalize_flags` + `cleanup` the alias table
            was built from.
        normalize_flags: `Normalize` flag
            set applied to the alias list at build time. Default
            `Normalize.CASEFOLD` matches production callers
            (nomenklatura/yente/FTM via `prenormalize_name`).
        cleanup: `Cleanup` variant applied
            during alias normalisation. Default `Cleanup.Noop`.
        generic: If True, substitute the generic form of the organisation
            type (e.g. ``llc``, ``jsc``) instead of the type-specific
            compare form. Specs without a `generic` field are left
            unchanged in generic mode.

    Returns:
        The text with recognised organisation types substituted. If every
        match would reduce the text to an empty string, the original
        text is returned unchanged.
    """
    return _replace_org_types_compare(name, int(normalize_flags), int(cleanup), generic)


def replace_org_types_display(
    name: str,
    normalize_flags: Normalize = Normalize.CASEFOLD | Normalize.SQUASH_SPACES,
    cleanup: Cleanup = Cleanup.Noop,
) -> str:
    """Replace organisation types in a name with their short display form.

    Spelt-out legal forms are shortened into common abbreviations
    (e.g. ``"Siemens Aktiengesellschaft"`` → ``"Siemens AG"``), preserving
    the case of non-matched portions. If the whole input is uppercase
    (`str.isupper()`), the whole output is re-uppercased.

    Matches case-insensitively across Unicode by casefolding a copy of
    the input internally for the match step — `normalize_flags` must
    therefore include `Normalize.CASEFOLD` so the alias table is
    casefolded too. The default does this.

    Args:
        name: The text to be processed.
        normalize_flags: `Normalize` flag
            set applied to the alias list at build time. Must include
            `Normalize.CASEFOLD` for Unicode-case-insensitive matching.
            Default `CASEFOLD | SQUASH_SPACES`.
        cleanup: `Cleanup` variant applied
            during alias normalisation. Default `Cleanup.Noop`.

    Returns:
        The text with recognised organisation types substituted for
        their display form. Non-matched regions keep their original case.
    """
    return _replace_org_types_display(name, int(normalize_flags), int(cleanup))


def remove_org_types(
    name: str,
    replacement: str = "",
    normalize_flags: Normalize = Normalize.CASEFOLD,
    cleanup: Cleanup = Cleanup.Noop,
) -> str:
    """Remove organisation-type designations from a name.

    Every recognised alias (LLC, Inc, GmbH, ...) in `name` is replaced
    with `replacement`. Useful as a preprocessing step when you want
    the entity name stripped of legal-form noise.

    Args:
        name: The text to be processed. Assumed to already be normalised
            with the same `normalize_flags` + `cleanup` the alias table
            was built from.
        replacement: The string to replace each matched alias with.
            Default ``""`` (strip).
        normalize_flags: `Normalize` flag
            set applied to the alias list at build time. Default
            `Normalize.CASEFOLD`.
        cleanup: `Cleanup` variant applied
            during alias normalisation. Default `Cleanup.Noop`.

    Returns:
        The text with recognised organisation types replaced. May be
        empty if the input consisted entirely of matched aliases and
        `replacement` is the empty string.
    """
    return _remove_org_types(name, int(normalize_flags), int(cleanup), replacement)


def extract_org_types(
    name: str,
    normalize_flags: Normalize = Normalize.CASEFOLD,
    cleanup: Cleanup = Cleanup.Noop,
    generic: bool = False,
) -> List[Tuple[str, str]]:
    """Find every organisation-type designation in a name.

    Scans `name` for recognised aliases (LLC, Inc, GmbH, ...) and returns
    the matched substring and its canonical target. A poor-person's
    "is this a company name?" detector.

    Args:
        name: The text to be processed. Assumed to already be normalised
            with the same `normalize_flags` + `cleanup` the alias table
            was built from.
        normalize_flags: `Normalize` flag
            set applied to the alias list at build time. Default
            `Normalize.CASEFOLD`.
        cleanup: `Cleanup` variant applied
            during alias normalisation. Default `Cleanup.Noop`.
        generic: If True, target values are the generic form (``llc``,
            ``jsc``) instead of the type-specific compare form. Matches
            :func:`replace_org_types_compare`.

    Returns:
        A list of ``(matched_text, target)`` tuples, one per
        non-overlapping match. Empty if nothing matches.
    """
    return _extract_org_types(name, int(normalize_flags), int(cleanup), generic)
