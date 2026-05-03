"""Symbol type and symbol-pairing helpers.

A [Symbol][rigour.names.symbol.Symbol] is a `(category, id)` pair
the tagger attaches to name parts: `NAME:Q4925477` for a recognised
person name, `ORG_CLASS:LLC` for a legal form, `INITIAL:j` for a
single-letter stand-in. Downstream matchers and indexers read them
to build semantic annotations on top of raw tokens.

[pair_symbols][rigour.names.symbol.pair_symbols] aligns the symbol
spans of two names into coverage-maximal pairings — the fast path
that lets matchers skip expensive string distance on tokens the
tagger has already explained on both sides. Each pairing is a tuple
of [Alignment][rigour.names.compare.Alignment]s carrying the shared
`Symbol`.

`Symbol.Category` is an alias for
[SymbolCategory][rigour.names.symbol.SymbolCategory]; either form
works for the nested-access pattern used across the OpenSanctions
stack.
"""

from rigour._core import Symbol, SymbolCategory
from rigour._core import pair_symbols

Symbol.Category = SymbolCategory


__all__ = ["Symbol", "SymbolCategory", "pair_symbols"]
