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

from rigour._core import Symbol, SymbolCategory

# Preserve the pre-port nested-class access pattern
# (`Symbol.Category.ORG_CLASS`) used across the stack. The enum type
# is identical to the top-level `SymbolCategory` — just two names for
# the same object.
Symbol.Category = SymbolCategory

__all__ = ["Symbol", "SymbolCategory"]
