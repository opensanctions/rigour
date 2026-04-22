"""Symbol type and symbol-pairing helpers.

A [Symbol][rigour.names.symbol.Symbol] is a `(category, id)` pair
the tagger attaches to name parts: `NAME:Q4925477` for a recognised
person name, `ORG_CLASS:LLC` for a legal form, `INITIAL:j` for a
single-letter stand-in. Downstream matchers and indexers read them
to build semantic annotations on top of raw tokens.

[pair_symbols][rigour.names.symbol.pair_symbols] aligns the symbol
spans of two names into coverage-maximal pairings — the fast path
that lets matchers skip expensive string distance on tokens the
tagger has already explained on both sides.

`Symbol.Category` is an alias for
[SymbolCategory][rigour.names.symbol.SymbolCategory]; either form
works for the nested-access pattern used across the OpenSanctions
stack.
"""

from dataclasses import dataclass
from typing import List, Tuple

from rigour._core import Symbol, SymbolCategory
from rigour._core import pair_symbols as _pair_symbols
from rigour.names.name import Name
from rigour.names.part import NamePart

Symbol.Category = SymbolCategory


@dataclass(frozen=True)
class SymbolEdge:
    """One paired span in a [pair_symbols][rigour.names.symbol.pair_symbols] alignment.

    Attributes:
        query_parts: `NamePart`s from `query.parts` that this edge
            covers. Same object references, not copies.
        result_parts: `NamePart`s from `result.parts` that this
            edge covers.
        symbol: The `Symbol` both sides carry.
    """

    query_parts: Tuple[NamePart, ...]
    result_parts: Tuple[NamePart, ...]
    symbol: Symbol


def pair_symbols(query: Name, result: Name) -> List[Tuple[SymbolEdge, ...]]:
    """Align the symbol spans of two names into coverage-maximal pairings.

    Reach for this when matching two tagged names and you want to
    skip Levenshtein on tokens the tagger has already explained —
    e.g. Latin "Vladimir" and Cyrillic "Владимир" both carrying
    the same `NAME:Q...` Putin symbol should pair without string
    comparison.

    Each returned pairing is a tuple of non-conflicting
    [SymbolEdge][rigour.names.symbol.SymbolEdge]s whose joint
    coverage is maximal within its scoring-equivalence class.
    Coverings that cover the same parts with the same category mix
    are collapsed to one; distinct category choices on the same
    parts (e.g. a token carrying both `NAME` and `SYMBOL`) surface
    as separate pairings.

    Args:
        query: The "left" name.
        result: The "right" name.

    Returns:
        One or more pairings. A single empty pairing `[()]` is
        returned when neither name has tagger output, when no
        symbol is shared between the two sides, or when either
        name has more than 64 parts. When the symbol layer found
        any shared evidence, only non-empty coverings are returned.
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
