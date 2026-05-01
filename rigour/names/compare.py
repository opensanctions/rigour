"""Residue-distance scoring for two `NamePart` lists.

Reach for [compare_parts][rigour.names.compare.compare_parts] when a
name matcher has already peeled off the parts it can explain by other
means — symbol pairing, alias tagging, identifier hits — and is left
with a residue that needs a fuzzy-match verdict (typo, transliteration
drift, surface-form variants of the same token).

The function returns one
[Alignment][rigour.names.compare.Alignment] per cluster of aligned
parts (paired or solo). Every input part appears in exactly one
alignment, so a caller can sum / weight / threshold the result
without losing track of which inputs got accounted for. Returned
alignments carry `symbol = None` (residue distance is non-symbolic
by definition).

The cost model penalises digit mismatches more than letter mismatches,
treats visually / phonetically confusable pairs (`0`/`o`, `1`/`l`,
`c`/`k`, …) as cheap edits, and charges almost nothing for token
merge / split. A length-dependent budget caps the per-side similarity
at zero once the total cost exceeds what's plausible for typo noise —
the matcher refuses to fuzzy-match when the edit-density crosses into
distinct-entity territory.

`fuzzy_tolerance` rescales the per-side budget. Higher = more
permissive (KYC-onboarding profile); lower = stricter (payment-
screening profile).
"""

from rigour._core import Alignment, compare_parts

__all__ = ["Alignment", "compare_parts"]
