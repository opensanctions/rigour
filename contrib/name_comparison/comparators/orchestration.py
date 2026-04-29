"""Orchestration: lifted match_name_symbolic shape, in pure Python.

Mirrors `nomenklatura.matching.logic_v2.names.match.match_name_symbolic`
minus the FtResult/Match data plumbing. Drives a (name1, name2, schema)
→ float Comparator that exercises the full pipeline:

  analyze_names  →  pair_symbols  →  symbol-edge clusters
                                 →  residue distance via compare_parts_orig
                                 →  weight policies (extra-name,
                                    family-name, stopword, literal-1.0)
                                 →  weighted-average aggregate
                                 →  best across pairings

This is throwaway scaffolding — when the spec settles and the Rust port
lands, the migration patches nomenklatura's match.py to call
`rigour.names.compare_parts` directly. The harness's orchestration here
exists so we can evaluate end-to-end behaviour on cases.csv during
iteration without depending on nomenklatura.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from followthemoney import model
from followthemoney.names import schema_type_tag
from rigour.names import (
    Name,
    NamePart,
    NamePartTag,
    NameTypeTag,
    Symbol,
    align_person_name_order,
    analyze_names,
)
from rigour.names.symbol import pair_symbols

from typing import Callable

from .compare_parts_orig import Comparison, compare_parts_orig

# A residue function takes (qry_parts, res_parts, bias) → list of
# Comparison-shaped records. Both the Python prototype and the Rust
# port adapter satisfy this protocol.
ResidueFn = Callable[[List[NamePart], List[NamePart], float], List[Comparison]]
from .policies import (
    EXTRA_QUERY_NAME,
    EXTRA_RESULT_NAME,
    FAMILY_NAME_WEIGHT,
    FUZZY_CUTOFF_FACTOR,
    SYM_SCORES,
    SYM_WEIGHTS,
    weight_extra_match,
)


@dataclass
class _Record:
    """One scored alignment record (pre-weight-aggregation).

    Symbol-edge records have `symbol` set; residue records (from
    compare_parts_orig) have `symbol=None`. The harness aggregates
    across all records per pairing.
    """

    qps: List[NamePart] = field(default_factory=list)
    rps: List[NamePart] = field(default_factory=list)
    score: float = 0.0
    weight: float = 1.0
    symbol: Symbol | None = None

    @property
    def is_family_name(self) -> bool:
        for np in self.qps:
            if np.tag == NamePartTag.FAMILY:
                return True
        for np in self.rps:
            if np.tag == NamePartTag.FAMILY:
                return True
        return False

    @property
    def weighted_score(self) -> float:
        return self.score * self.weight


def _schema_to_tag(schema: str) -> NameTypeTag:
    sch = model.get(schema)
    if sch is None:
        return NameTypeTag.UNK
    return schema_type_tag(sch)


def _match_name_symbolic(
    query: Name, result: Name, bias: float, residue_fn: ResidueFn
) -> float:
    """Lifted from logic_v2/names/match.py:match_name_symbolic.

    Returns the best aggregate score across all pairings produced by
    pair_symbols. Each pairing produces a list of weighted records;
    the pairing's score is sum(weighted_score) / sum(weight).

    `residue_fn` is the swappable residue-distance function — either
    the Python prototype (`compare_parts_orig`) or a Rust adapter
    (`compare_rust._rust_residue`). Both have the same signature.
    """
    best = 0.0

    for edges in pair_symbols(query, result):
        records: List[_Record] = []

        # Stage 1: build records from symbol edges. Score and weight
        # come from the per-category tables — no string distance.
        for edge in edges:
            records.append(
                _Record(
                    qps=list(edge.query_parts),
                    rps=list(edge.result_parts),
                    score=SYM_SCORES.get(edge.symbol.category, 1.0),
                    weight=SYM_WEIGHTS.get(edge.symbol.category, 1.0),
                    symbol=edge.symbol,
                )
            )

        # Stage 2: residue — parts not covered by any edge in this
        # pairing. Run them through compare_parts_orig.
        query_used: Set[NamePart] = {p for edge in edges for p in edge.query_parts}
        result_used: Set[NamePart] = {p for edge in edges for p in edge.result_parts}
        query_rem = [p for p in query.parts if p not in query_used]
        result_rem = [p for p in result.parts if p not in result_used]

        if query_rem or result_rem:
            if query.tag == NameTypeTag.PER:
                query_rem, result_rem = align_person_name_order(query_rem, result_rem)
            else:
                query_rem = NamePart.tag_sort(query_rem)
                result_rem = NamePart.tag_sort(result_rem)

            for comp in residue_fn(query_rem, result_rem, bias):
                records.append(
                    _Record(qps=list(comp.qps), rps=list(comp.rps), score=comp.score, weight=1.0)
                )

        # Stage 3: weight policies on every record (symbol-edge AND
        # residue). Mirrors match_name_symbolic exactly.
        for rec in records:
            if not rec.qps:
                # Unmatched result-side part
                rec.weight = EXTRA_RESULT_NAME * weight_extra_match(rec.rps, result)
            elif not rec.rps:
                # Unmatched query-side part
                rec.weight = EXTRA_QUERY_NAME * weight_extra_match(rec.qps, query)

            # Literal-equality override: paired records whose comparable
            # forms match exactly always score 1.0, regardless of what
            # the symbol or distance computation produced.
            if (
                rec.score < 1.0
                and len(rec.qps) == len(rec.rps)
                and rec.qps
                and all(q.comparable == r.comparable for q, r in zip(rec.qps, rec.rps))
            ):
                rec.score = 1.0

            if rec.is_family_name:
                rec.weight *= FAMILY_NAME_WEIGHT

        # Stage 4: aggregate this pairing.
        total_weight = sum(r.weight for r in records)
        total_score = sum(r.weighted_score for r in records)
        score = total_score / total_weight if total_weight > 0 else 0.0

        if score > best:
            best = score
            if best == 1.0:
                break

    return best


def compare_python_via(
    name1: str, name2: str, schema: str, *, residue_fn: ResidueFn
) -> float:
    """Comparator factory: orchestration around any residue function.

    `residue_fn` swaps between the Python prototype and the Rust port
    adapter. Both `compare_python` and `compare_rust` are thin
    wrappers over this with their own residue function bound.
    """
    type_tag = _schema_to_tag(schema)
    if type_tag == NameTypeTag.UNK:
        return 0.0

    qry_set = analyze_names(type_tag, [name1])
    res_set = analyze_names(type_tag, [name2])
    if not qry_set or not res_set:
        return 0.0

    # Literal short-circuit on comparable form, like name_match in
    # logic_v2 — prevents borderline-fuzzy outputs on pairs whose
    # comparable forms collapse to the same string.
    qry_comparable = {n.comparable: n for n in qry_set}
    res_comparable = {n.comparable: n for n in res_set}
    if set(qry_comparable).intersection(res_comparable):
        return 1.0

    # Cross-product over alias bags. cases.csv currently always has
    # one Name per side, but the loop costs nothing and matches what
    # name_match does.
    best = 0.0
    for qry_name in qry_set:
        for res_name in res_set:
            score = _match_name_symbolic(
                qry_name, res_name, FUZZY_CUTOFF_FACTOR, residue_fn
            )
            if score > best:
                best = score
                if best == 1.0:
                    return best
    return best


def _python_residue(qry_parts, res_parts, bias) -> List[Comparison]:
    return compare_parts_orig(qry_parts, res_parts, bias=bias)


def compare_python(name1: str, name2: str, schema: str) -> float:
    """Comparator: full Python pipeline using compare_parts_orig as residue."""
    return compare_python_via(name1, name2, schema, residue_fn=_python_residue)
