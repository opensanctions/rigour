"""
Levels of government: where a public body or position sits within its polity, from
global organisations down to municipalities. Use these to tag jurisdictions and to state
which tiers a rule (e.g. a PEP definition) applies to.

A level is not an administrative depth (ADM1, ADM2, ...): depth says where a unit sits
in a gazetteer, level says what kind of government it is. Administrative tiers without
a government of their own (German Regierungsbezirke, French arrondissements) have no
level, and countries without a middle tier skip `SUBREGIONAL`. A jurisdiction can hold
several levels, e.g. Berlin is both `REGIONAL` and `MUNICIPAL`.
"""

INTERNATIONAL = "international"
"""Organisations of states without a legal order of their own: UN, IMF, NATO."""

SUPRANATIONAL = "supranational"
"""Unions of states that form a jurisdiction with binding organs: the EU, WAEMU."""

NATIONAL = "national"
"""Top tier of a sovereign state, a de facto state, or a dependency with its own
AML regime (Jersey, Hong Kong)."""

REGIONAL = "regional"
"""First tier below national: states, Länder, provinces, oblasts, Scotland."""

SUBREGIONAL = "subregional"
"""Tier between regional and municipal: Kreise, départements, US counties."""

MUNICIPAL = "municipal"
"""Lowest tier of general-purpose government: cities, communes, Gemeinden."""

LEVELS: dict[str, str] = {
    INTERNATIONAL: "International",
    SUPRANATIONAL: "Supranational",
    NATIONAL: "National",
    REGIONAL: "Regional",
    SUBREGIONAL: "Subregional",
    MUNICIPAL: "Municipal",
}
"""Labels for each level, ordered from the widest to the narrowest tier."""
