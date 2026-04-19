"""Rust-backed sibling of `rigour.names.org_types.replace_org_types_compare`.

Exists side-by-side with the Python implementation so callers and
`benchmarks/bench_org_types.py` can A/B them before deciding to
replace the Python path.

The `normalize_flags` / `cleanup` parameters select which compiled
regex is used by Rust — they control how the alias list was normalised
at regex-build time. The caller is expected to normalise its runtime
input with the same flags before calling. See `plans/rust-normalizer.md`
("Reference-data normalisation: keep the override, as flags") for the
full design.

Default flags match what nomenklatura, yente, and FTM pass in practice
today (`normalizer=prenormalize_name` ≡ casefold-only). The old Python
default (`_normalize_compare` ≡ squash+casefold) is one
`Normalize.CASEFOLD | Normalize.SQUASH_SPACES` away if you need it.
"""

from rigour._core import replace_org_types_compare as _replace
from rigour.text.normalize import Cleanup, Normalize

__all__ = ["replace_org_types_compare"]


def replace_org_types_compare(
    name: str,
    normalize_flags: Normalize = Normalize.CASEFOLD,
    cleanup: Cleanup = Cleanup.Noop,
) -> str:
    """Replace organisation types in `name` with their compare-form targets.

    Assumes `name` has already been normalised with `normalize_flags` (+
    `cleanup`) by the caller. The flags also drive how aliases were
    normalised when the internal regex was compiled — Rust caches one
    regex per `(normalize_flags, cleanup)` combination.
    """
    return _replace(name, int(normalize_flags), int(cleanup))
