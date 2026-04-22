"""Symbol type — a semantic interpretation applied to one or more parts
of a name.

Rust-backed via `rigour._core`; the actual struct is a 24-byte
`{ category: SymbolCategory, id: Arc<str> }` with a global string
interner behind the id — symbols are heavily duplicated across
tagged names (every "John" part carries the same `NAME:Q4925477`
symbol) and interning the id keeps the per-`Name` footprint flat.

The class is exposed as `rigour.names.Symbol`; the category enum lives
as both `rigour.names.SymbolCategory` and `Symbol.Category` (the
pre-port nested-class access pattern used across rigour, FTM,
nomenklatura, and yente).

Breaking change vs. the pre-port Python implementation: `Symbol.id`
is always `str`. Ids originally passed as `int` are decimal-stringified
at construction. Downstream code that compared `symbol.id` against an
int literal needs to compare against the string form.
"""

from dataclasses import dataclass
from typing import List, Tuple

from rigour._core import Symbol, SymbolCategory
from rigour._core import pair_symbols as _pair_symbols
from rigour.names.name import Name
from rigour.names.part import NamePart

# Preserve the pre-port nested-class access pattern
# (`Symbol.Category.ORG_CLASS`) used across the stack. The enum type
# is identical to the top-level `SymbolCategory` — just two names for
# the same object.
Symbol.Category = SymbolCategory


@dataclass(frozen=True)
class SymbolEdge:
    """One paired span in a [pair_symbols][rigour.names.symbol.pair_symbols] alignment.

    `query_parts` and `result_parts` are the `NamePart`s covered on
    each side (same references as in `query.parts` / `result.parts`).
    `symbol` is the shared `Symbol` the two spans carry. Frozen so
    pairings are hashable and safe to dedup.
    """

    query_parts: Tuple[NamePart, ...]
    result_parts: Tuple[NamePart, ...]
    symbol: Symbol


def pair_symbols(query: Name, result: Name) -> List[Tuple[SymbolEdge, ...]]:
    """Align the symbol spans of two names into coverage-maximal pairings.

    Used by name-matching pipelines to short-cut expensive string
    distance on the portions of two names that the tagger has already
    explained with a shared symbol — e.g. Latin "Vladimir" and
    Cyrillic "Владимир" both carrying `NAME:QxxxxxPutin` don't need
    Levenshtein comparison.

    Returns a list of pairings; each pairing is a tuple of
    non-conflicting [SymbolEdge][rigour.names.symbol.SymbolEdge]s
    whose joint coverage is maximal within its equivalence class.
    When any candidate edge survives, only non-empty coverings are
    returned; the empty tuple is emitted only as a fallback when
    no symbol evidence is available (no tagger output on either
    side, no shared symbols, or more than 64 tokens on a name).
    """
    q_parts = query.parts
    r_parts = result.parts
    raw = _pair_symbols(query, result)
    return [
        tuple(
            SymbolEdge(
                query_parts=tuple(q_parts[i] for i in edge.query_parts),
                result_parts=tuple(r_parts[i] for i in edge.result_parts),
                symbol=edge.symbol,
            )
            for edge in pairing
        )
        for pairing in raw
    ]


__all__ = ["Symbol", "SymbolCategory", "SymbolEdge", "pair_symbols"]
