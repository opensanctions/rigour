"""Matcher-policy constants lifted from nomenklatura's logic_v2.

These are read-only matcher policy that the harness reproduces locally
during phase 2 so we don't have a circular dependency on nomenklatura.
The original lives in `nomenklatura/matching/logic_v2/names/magic.py`
and `model.py`; sync manually if logic_v2's defaults change.

Frozen during iteration: any one of these changing would be a logic_v2
change, not a name-distance change. Listed here for visibility, not
for tuning.
"""

from __future__ import annotations

from typing import Dict, List

from rigour.names import Name, NamePart, Symbol
from rigour.text import is_stopword


# --- ScoringConfig defaults from logic_v2/model.py -------------------------

EXTRA_QUERY_NAME = 0.8
EXTRA_RESULT_NAME = 0.2
FAMILY_NAME_WEIGHT = 1.3
FUZZY_CUTOFF_FACTOR = 1.0


# --- Symbol score / weight tables from logic_v2/names/magic.py -------------

# Score per symbol category (used as the Comparison.score for symbol-edge
# records — not derived from string distance, since the tagger has
# already asserted these parts label the same thing).
SYM_SCORES: Dict[Symbol.Category, float] = {
    Symbol.Category.ORG_CLASS: 0.8,
    Symbol.Category.INITIAL: 0.9,
    Symbol.Category.NAME: 0.9,
    Symbol.Category.NICK: 0.6,
    Symbol.Category.SYMBOL: 0.9,
    Symbol.Category.DOMAIN: 0.9,
    Symbol.Category.NUMERIC: 0.9,
    Symbol.Category.LOCATION: 0.9,
}

# Weight per symbol category for two-sided matches. Modulates how much
# weight a symbol-edge record carries in the final aggregate. NUMERIC is
# >1 because vessel/fund numbers are highly discriminative.
SYM_WEIGHTS: Dict[Symbol.Category, float] = {
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.INITIAL: 0.5,
    Symbol.Category.NICK: 0.8,
    Symbol.Category.SYMBOL: 0.3,
    Symbol.Category.DOMAIN: 0.7,
    Symbol.Category.NUMERIC: 1.3,
    Symbol.Category.LOCATION: 0.8,
}

# Weight overrides for one-sided (unmatched) parts — used inside
# weight_extra_match. ORG_CLASS / SYMBOL on an unmatched part is cheap
# (the part is "Siemens AG vs Siemens" — losing the AG is fine);
# NUMERIC on an unmatched part is expensive (PE Fund 1 vs PE Fund —
# the digit identifies the specific entity).
EXTRAS_WEIGHTS: Dict[Symbol.Category, float] = {
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.SYMBOL: 0.7,
    Symbol.Category.NUMERIC: 1.3,
    Symbol.Category.LOCATION: 0.8,
}


def weight_extra_match(parts: List[NamePart], name: Name) -> float:
    """Per-side bias on an unmatched-parts record's weight.

    Walks the source Name's spans looking for a span whose parts are
    exactly the unmatched set; if found, multiplies in the EXTRAS_WEIGHTS
    override for that span's symbol category. Stopword-only single parts
    get a flat 0.5. Mirrors logic_v2/names/magic.py:weight_extra_match.
    """
    if len(parts) == 1 and is_stopword(parts[0].form):
        return 0.5
    sparts = hash(tuple(parts))
    weight = 1.0
    for span in name.spans:
        if span.symbol.category == Symbol.Category.NUMERIC:
            part = span.parts[0]
            if len(span.parts) == 1 and not part.numeric and len(part.comparable) < 2:
                continue
        if sparts == hash(tuple(span.parts)):
            weight = weight * EXTRAS_WEIGHTS.get(span.symbol.category, 1.0)
    return weight
