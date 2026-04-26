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
   or the AC tagger inside
   [analyze_names][rigour.names.analyze_names]) builds an internal
   regex/automaton from static YAML data (aliases, stopwords, AC
   patterns) and uses `normalize_flags` + `cleanup` to decide how
   that static data gets normalised at build time. The caller is
   expected to normalise its runtime input with the *same* flags
   before calling. Functions in this bucket cache one compiled
   automaton per distinct flag combination.

## Pipeline order

Steps run in a fixed order regardless of bit-ordering in the flag
value:

    1. STRIP                — trim leading/trailing whitespace
    2. NFKD / NFKC / NFC    — at most one is meaningful; if multiple
                              are set, Rust applies the first one
                              listed in its dispatch (NFKD)
    3. CASEFOLD             — Unicode full casefold (ß → ss, not lowercase)
    4. Cleanup              — category_replace, unless Cleanup.Noop
    5. SQUASH_SPACES        — collapse whitespace runs, trim ends
    6. NAME                 — tokenize via
                              [tokenize_name][rigour.names.tokenize.tokenize_name]
                              and rejoin with a single ASCII space

Transliteration is NOT part of this pipeline. rigour's public
transliteration surface is [rigour.text.translit][] — opportunistic,
limited to Latin/Cyrillic/Greek/Armenian/Georgian/Hangul. For
broader-script lossy romanisation use
`normality.ascii_text` / `normality.latinize_text`.

Empty output is coalesced to ``None``, matching the contract of the
pre-flags `Optional[str]` normalisers.

## Common compositions

The flag sets pinned as defaults across the rigour API:

* **`Normalize.CASEFOLD`** — production default for comparison
  keys that should preserve whitespace and script.
* **`Normalize.CASEFOLD | Normalize.SQUASH_SPACES`** — adds
  whitespace collapsing on top. Used when input whitespace is
  unreliable, and by display-style replacers that need
  case-insensitive matching with tidied whitespace.
* **`Normalize.SQUASH_SPACES`** — whitespace-tidy without case
  change. Used by display-form replacers that want to preserve
  caller case.
* **`Normalize.CASEFOLD | Normalize.NAME`** — casefold and
  tokenise with [rigour.names.tokenize.tokenize_name][], yielding
  a stable space-separated name key for matching.

## Implementation note

The actual work runs in Rust via `rigour._core._normalize`. This
module is the idiomatic Python surface — `IntFlag` for the bit set,
`IntEnum` for the variant, both crossing the FFI boundary as plain
ints at ~zero marshalling cost.
"""

from enum import IntEnum, IntFlag
from typing import Callable, Optional

from rigour._core import _normalize

__all__ = ["normalize", "Normalize", "Cleanup", "Normalizer", "noop_normalizer"]


#: Normalizer protocol — callable mapping optional string to
#: optional string, where `None` means "nothing meaningful here."
#: Used by parametric predicates
#: ([rigour.text.stopwords.is_stopword][] / `is_nullword` /
#: `is_nullplace`,
#: [rigour.names.check.is_generic_person_name][]) so callers can
#: plug in whatever normalisation shape they need — both the
#: wordlist build and runtime lookups must use the same callable.
Normalizer = Callable[[Optional[str]], Optional[str]]


def noop_normalizer(text: Optional[str]) -> Optional[str]:
    """Identity normalizer that strips whitespace and rejects empty.

    Default :data:`Normalizer` for callers whose input is already
    in the desired shape — only edge whitespace is removed.

    Args:
        text: A string, or `None`.

    Returns:
        The stripped string, or `None` for `None` input or
        empty / whitespace-only input.
    """
    if text is None:
        return None
    text = text.strip()
    if len(text) == 0:
        return None
    return text


class Normalize(IntFlag):
    """Bit-flag set selecting individual normalisation steps.

    Compose flags with bitwise OR and pass to [normalize][rigour.text.normalize.normalize] or to
    any rigour function that exposes a `normalize_flags=` parameter
    (e.g. :func:`rigour.names.org_types.replace_org_types_compare`).
    See the module docstring for the fixed pipeline order the flags
    compose into and for common flag compositions.

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
            Splits composed characters apart. Mutually exclusive
            with NFC/NFKC.
        NAME: Run the string through
            [tokenize_name][rigour.names.tokenize.tokenize_name]
            and rejoin the tokens with a single ASCII space. Runs
            as the final pipeline step, so it also subsumes
            whitespace squashing.
    """

    # Bit values MUST match rust/src/text/normalize.rs `bitflags! Normalize`.
    STRIP = 1 << 0
    SQUASH_SPACES = 1 << 1
    CASEFOLD = 1 << 2
    NFC = 1 << 3
    NFKC = 1 << 4
    NFKD = 1 << 5
    NAME = 1 << 6


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
        Slug: URL-slug-style cleanup. Differs from `Strong` in two
            places: preserves modifier letters (Lm) and nonspacing
            marks (Mn) that `Strong` deletes, and deletes control
            characters (Cc) that `Strong` turns into whitespace. Use
            for stopword keys and slug generation.
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
        The normalised string, or ``None`` if `text` was ``None``
        or if the pipeline reduced the text to an empty string.
        The empty-output-to-``None`` coalescence is the
        Optional-string contract.
    """
    if text is None:
        return None
    return _normalize(text, int(flags), int(cleanup))
