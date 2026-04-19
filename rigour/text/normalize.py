"""Flag-based text normalisation — the canonical reference for the
`normalize_flags` / `cleanup` parameters used across rigour.

This module exposes three things:

* [Normalize][rigour.text.normalize.Normalize] — a bit-flag set selecting individual normalisation
  steps (strip, casefold, NFC/NFKC/NFKD, transliterate, squash spaces).
* [Cleanup][rigour.text.normalize.Cleanup] — an enum picking one of two fixed Unicode-category
  replacement profiles (`Strong`, `Slug`), or `Noop` to skip the step.
* [normalize][rigour.text.normalize.normalize] — the single entry point that runs the composed
  pipeline on a string.

## Two distinct uses of these flags

The same `Normalize` vocabulary shows up in two places across rigour,
with different lifecycles:

1. **Input normalisation.** The caller runs
   `normalize(text, flags, cleanup)` on a single runtime string and
   passes the result downstream. This is what this module does
   directly.
2. **Reference-data normalisation.** A lookup/tagger function (e.g.
   [replace_org_types_compare][rigour.names.org_types.replace_org_types_compare],
   [tag_org_name][rigour.names.tagging.tag_org_name]) builds an
   internal regex/automaton from static YAML data (aliases, stopwords,
   AC patterns) and uses `normalize_flags` + `cleanup` to decide how
   that static data gets normalised at build time. The caller is
   expected to normalise its runtime input with the *same* flags
   before calling. Functions in this bucket cache one compiled
   automaton per distinct flag combination.

See `plans/rust-normalizer.md` for the full design rationale.

## Pipeline order

Steps run in a fixed order regardless of bit-ordering in the flag
value:

    1. STRIP                — trim leading/trailing whitespace
    2. NFKD / NFKC / NFC    — at most one is meaningful; if multiple
                              are set, Rust applies the first one
                              listed in its dispatch (NFKD)
    3. CASEFOLD             — Unicode full casefold (ß → ss, not lowercase)
    4. ASCII or LATIN       — ASCII wins if both are set
    5. Cleanup              — category_replace, unless Cleanup.Noop
    6. SQUASH_SPACES        — collapse whitespace runs, trim ends

Empty output is coalesced to ``None``, matching the contract of the
pre-flags `Optional[str]` normalisers.

## Common compositions

These are the flag sets in use across rigour, FTM, nomenklatura, and
yente — the defaults on
[replace_org_types_compare][rigour.names.org_types.replace_org_types_compare]
and friends are pinned to these:

* **Casefold-only (`Normalize.CASEFOLD`)** — production default.
  Equivalent to the pre-flags `prenormalize_name`. Used to build
  comparison keys while preserving whitespace and script.
* **Casefold + squash (`Normalize.CASEFOLD | Normalize.SQUASH_SPACES`)**
  — the pre-flags `_normalize_compare`. Adds whitespace collapsing on
  top of casefold; useful when input whitespace is unreliable.
* **Squash-only (`Normalize.SQUASH_SPACES`)** — the pre-flags
  `normalize_display`. Whitespace-tidies without touching case, used
  by display-form replacers that want to preserve caller case.
* **Full match key (`Normalize.CASEFOLD | Normalize.ASCII | Normalize.SQUASH_SPACES`
  + `Cleanup.Strong`)** — aggressive match-key builder that collapses
  diacritics and punctuation. Used for stopword lookup and similar
  "I want the roughest possible shape" workflows.

## Implementation note

The actual work runs in Rust via `rigour._core._normalize`. This
module is the idiomatic Python surface — `IntFlag` for the bit set,
`IntEnum` for the variant, both crossing the FFI boundary as plain
ints at ~zero marshalling cost.
"""
from enum import IntEnum, IntFlag
from typing import Optional

from rigour._core import _normalize

__all__ = ["normalize", "Normalize", "Cleanup"]


class Normalize(IntFlag):
    """Bit-flag set selecting individual normalisation steps.

    Compose flags with bitwise OR and pass to [normalize][rigour.text.normalize.normalize] or to
    any rigour function that exposes a `normalize_flags=` parameter
    (e.g. :func:`rigour.names.org_types.replace_org_types_compare`,
    :func:`rigour.names.tagging.tag_org_name`). See the module
    docstring for the fixed pipeline order the flags compose into
    and for common flag compositions.

    Attributes:
        STRIP: Trim leading and trailing whitespace.
        SQUASH_SPACES: Collapse runs of whitespace (including newlines,
            tabs, Unicode whitespace) into single spaces and trim the
            edges. Runs as the final pipeline step, so cleaning up
            whitespace introduced by earlier steps (e.g. category
            replacement) comes out right.
        CASEFOLD: Unicode full casefold (e.g. ``ß → ss``). This is
            *not* the same as `str.lower()` — casefold is the correct
            tool for case-insensitive comparison across Unicode.
        NFC: Apply Unicode Normal Form C (canonical composition).
            Rarely needed on its own; most callers want NFKC or NFKD.
            Mutually exclusive with NFKC/NFKD.
        NFKC: Apply Unicode Normal Form KC (compatibility composition).
            Folds compatibility variants (e.g. full-width digits → ASCII)
            while keeping a composed form. Mutually exclusive with
            NFC/NFKD.
        NFKD: Apply Unicode Normal Form KD (compatibility decomposition).
            Splits composed characters apart — useful when the next
            step strips marks (ASCII does this). Mutually exclusive
            with NFC/NFKC.
        LATIN: Transliterate to Latin script, preserving diacritics.
            No-op on text already in Latin script. Implemented by
            dispatching to per-script ICU4X transliterators. See
            [latinize_text][rigour.text.transliteration.latinize_text].
        ASCII: Transliterate all the way to ASCII — includes LATIN
            plus NFKD + nonspacing-mark stripping + a fallback table
            for ø→o, ß→ss, etc. ASCII is a superset of LATIN; setting
            both is equivalent to setting ASCII alone. See
            [ascii_text][rigour.text.transliteration.ascii_text].
    """

    # Bit values MUST match rust/src/text/normalize.rs `bitflags! Normalize`.
    STRIP = 1 << 0
    SQUASH_SPACES = 1 << 1
    CASEFOLD = 1 << 2
    NFC = 1 << 3
    NFKC = 1 << 4
    NFKD = 1 << 5
    LATIN = 1 << 6
    ASCII = 1 << 7


class Cleanup(IntEnum):
    """Unicode-category-based cleanup variants.

    `Cleanup` picks one of a small set of fixed category → action
    tables that drive the pipeline's `category_replace` step
    (pipeline step 5). The step rewrites or deletes characters based
    on their Unicode general category (e.g. punctuation, control,
    mark, symbol). The tables are deliberately closed — callers
    compose via the flag set, not by passing ad-hoc category maps.

    Attributes:
        Noop: Skip the `category_replace` step entirely. The default
            for all rigour functions that expose `cleanup`.
        Strong: Aggressive cleanup — punctuation and symbols become
            whitespace; controls, formats, and marks are deleted. Use
            when you want a matching key stripped of all decoration.
        Slug: URL-slug-style cleanup — similar to `Strong` but
            preserves modifier letters (Lm) and nonspacing marks (Mn).
            Use for stopword keys and slug generation.
    """

    # Values MUST match the tag encoding in rust/src/lib.rs py_normalize().
    Noop = 0
    Strong = 1
    Slug = 2


def normalize(
    text: Optional[str],
    flags: Normalize = Normalize(0),
    cleanup: Cleanup = Cleanup.Noop,
) -> Optional[str]:
    """Apply a composed sequence of text normalisation steps.

    The pipeline order and semantics of each flag are described in the
    module docstring. This function is the canonical entry point;
    other rigour functions that take `normalize_flags=` + `cleanup=`
    apply the same pipeline to their internal reference data at
    regex/automaton build time.

    Args:
        text: The text to normalise. If ``None``, the function
            short-circuits to ``None`` without calling into Rust.
        flags: Which normalisation steps to apply (see `Normalize`).
            Default ``Normalize(0)`` runs no steps — the function is
            effectively a type-safe identity under the default, use
            explicit flags to do work.
        cleanup: Which category-replacement variant to apply as the
            fifth pipeline step (see `Cleanup`). Default `Cleanup.Noop`
            skips that step.

    Returns:
        The normalised string, or ``None`` if `text` was ``None`` or
        if the pipeline reduced the text to an empty string. The
        empty-output-to-``None`` coalescence matches the contract of
        the pre-flags Python normalisers.
    """
    if text is None:
        return None
    return _normalize(text, int(flags), int(cleanup))
