"""compare_parts_orig — Python prototype of the residue-distance primitive.

The `_orig` suffix marks this as the original Python reference; the
unsuffixed name `compare_parts` is reserved for the eventual Rust port
in `rigour.names.compare_parts`. Phase 2 (spec iteration) operates on
this file's body. When the Rust port lands, both run side-by-side in
the harness so per-case `qsv diff` is the parity check.

The prototype is structured as three internal stages so each spec
decision is one function-swap away:

- `_align`: cost-folded alignment over the joined NamePart strings.
  Cost model lives here.
- `_cluster`: pair (qry_part, res_part) into Comparison records.
  Pairing rule lives here.
- `_score`: per-cluster score from the per-part costs gathered during
  alignment. Combination function and length budget live here.

The first iteration in this file is a faithful port of nomenklatura's
`weighted_edit_similarity` (Levenshtein opcodes + 0.51 overlap
threshold + product of per-side similarities + log-2.35 budget). Spec
iterations swap one of the three internal stages and register a new
variant in `COMPARATORS`.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import chain, zip_longest
from typing import Dict, List, Set, Tuple

from rapidfuzz.distance import Levenshtein
from rigour.names import NamePart


# Token boundary in the joined string used by the alignment.
SEP = " "

# Visual / phonetic confusable pairs. Substituting / inserting / deleting
# one for the other gets the confusable cost tier (cheaper than a normal
# edit). Mirror of nomenklatura's SIMILAR_PAIRS — eventually moves to
# resources/names/compare.yml as a shared resource.
_SIMILAR_PAIRS_RAW: List[Tuple[str, str]] = [
    ("0", "o"),
    ("1", "i"),
    ("g", "9"),
    ("q", "9"),
    ("b", "6"),
    ("5", "s"),
    ("e", "i"),
    ("1", "l"),
    ("o", "u"),
    ("i", "j"),
    ("i", "y"),
    ("c", "k"),
    ("n", "h"),
]
SIMILAR_PAIRS: Set[Tuple[str, str]] = set(_SIMILAR_PAIRS_RAW) | {
    (b, a) for a, b in _SIMILAR_PAIRS_RAW
}


# Multiplier on the per-side cost budget — higher = more permissive
# (more edits tolerated before the score caps to zero), lower =
# stricter. logic_v2 plumbs this via `nm_fuzzy_cutoff_factor` on
# ScoringConfig; hard-coded here for the prototype.
DEFAULT_FUZZY_TOLERANCE = 1.0


@dataclass
class Comparison:
    """One alignment cluster.

    Either a paired record (both sides non-empty) representing a
    set of query parts that align with a set of result parts, or a
    solo record (one side empty, the other a single part)
    representing an unmatched part.
    """

    qps: List[NamePart] = field(default_factory=list)
    rps: List[NamePart] = field(default_factory=list)
    score: float = 0.0


# ---------------------------------------------------------------------------
# Stage 1: alignment
# ---------------------------------------------------------------------------


def _edit_cost(op: str, qc: str | None, rc: str | None) -> float:
    """Char-pair cost lookup. Mirrors nomenklatura's `_edit_cost`."""
    if op == "equal":
        return 0.0
    if qc == SEP and rc is None:
        return 0.2
    if rc == SEP and qc is None:
        return 0.2
    if (qc, rc) in SIMILAR_PAIRS:
        return 0.7
    if qc is not None and qc.isdigit():
        return 1.5
    if rc is not None and rc.isdigit():
        return 1.5
    return 1.0


@dataclass
class _AlignmentData:
    """Per-part cost streams + per-pair overlap counts.

    Output of stage 1 (`_align`); consumed by stages 2 (`_cluster`)
    and 3 (`_score`).
    """

    qry_costs: Dict[NamePart, List[float]]
    res_costs: Dict[NamePart, List[float]]
    overlaps: Dict[Tuple[NamePart, NamePart], int]


def _align(qry_parts: List[NamePart], res_parts: List[NamePart]) -> _AlignmentData:
    """Walk Levenshtein opcodes char-by-char, accumulating per-part costs
    and per-pair overlap counts.

    The current implementation uses unit-cost Levenshtein opcodes from
    rapidfuzz (the alignment is optimal under unit costs, then re-scored
    via `_edit_cost`). The Rust port will switch to cost-folded
    Wagner-Fischer (alignment optimal under the actual cost model) — see
    `plans/weighted-distance.md` § Cost-folded DP.
    """
    qry_costs: Dict[NamePart, List[float]] = defaultdict(list)
    res_costs: Dict[NamePart, List[float]] = defaultdict(list)
    overlaps: Dict[Tuple[NamePart, NamePart], int] = defaultdict(int)

    if not qry_parts or not res_parts:
        return _AlignmentData(qry_costs, res_costs, overlaps)

    qry_text = SEP.join(p.comparable for p in qry_parts)
    res_text = SEP.join(p.comparable for p in res_parts)

    qry_idx = 0
    res_idx = 0
    qry_cur = qry_parts[0]
    res_cur = res_parts[0]

    for op in Levenshtein.opcodes(qry_text, res_text):
        qry_span = qry_text[op.src_start : op.src_end]
        res_span = res_text[op.dest_start : op.dest_end]
        for qc, rc in zip_longest(qry_span, res_span, fillvalue=None):
            if op.tag == "equal":
                if qc not in (None, SEP) and rc not in (None, SEP):
                    overlaps[(qry_cur, res_cur)] += 1
            cost = _edit_cost(op.tag, qc, rc)
            if qc is not None:
                qry_costs[qry_cur].append(cost)
                if qc == SEP:
                    qry_idx += 1
                    if qry_idx < len(qry_parts):
                        qry_cur = qry_parts[qry_idx]
            if rc is not None:
                res_costs[res_cur].append(cost)
                if rc == SEP:
                    res_idx += 1
                    if res_idx < len(res_parts):
                        res_cur = res_parts[res_idx]

    return _AlignmentData(qry_costs, res_costs, overlaps)


# ---------------------------------------------------------------------------
# Stage 2: clustering
# ---------------------------------------------------------------------------


@dataclass
class _Cluster:
    qps: List[NamePart] = field(default_factory=list)
    rps: List[NamePart] = field(default_factory=list)


def _cluster(
    qry_parts: List[NamePart],
    res_parts: List[NamePart],
    align: _AlignmentData,
) -> List[_Cluster]:
    """Pair `(qry_part, res_part)` into clusters via the 0.51 overlap rule
    with transitive closure.

    Mirrors nomenklatura's `weighted_edit_similarity` clustering: a pair
    joins an existing cluster if either part is already in one;
    otherwise a fresh cluster is created. Unmatched parts at the end
    surface as solo `_Cluster`s (one side empty).
    """
    part_to_cluster: Dict[NamePart, _Cluster] = {}

    for (qp, rp), overlap in align.overlaps.items():
        min_len = min(len(qp.comparable), len(rp.comparable))
        if min_len == 0:
            continue
        if overlap / min_len > 0.51:
            cluster = part_to_cluster.get(qp) or part_to_cluster.get(rp) or _Cluster()
            if qp not in cluster.qps:
                cluster.qps.append(qp)
            if rp not in cluster.rps:
                cluster.rps.append(rp)
            part_to_cluster[qp] = cluster
            part_to_cluster[rp] = cluster

    seen_ids: Set[int] = set()
    clusters: List[_Cluster] = []
    for cluster in part_to_cluster.values():
        if id(cluster) not in seen_ids:
            seen_ids.add(id(cluster))
            clusters.append(cluster)

    matched_qps = {qp for c in clusters for qp in c.qps}
    matched_rps = {rp for c in clusters for rp in c.rps}
    for qp in qry_parts:
        if qp not in matched_qps:
            clusters.append(_Cluster(qps=[qp]))
    for rp in res_parts:
        if rp not in matched_rps:
            clusters.append(_Cluster(rps=[rp]))

    return clusters


# ---------------------------------------------------------------------------
# Stage 3: scoring
# ---------------------------------------------------------------------------


def _costs_similarity(costs: List[float], fuzzy_tolerance: float = DEFAULT_FUZZY_TOLERANCE) -> float:
    """Per-side similarity from accumulated char-level costs.

    `1 - total_cost / len(costs)`, gated by a length-dependent budget
    cap (`log_{2.35}(max(len-2, 1)) * fuzzy_tolerance`). The log floor disables
    fuzzy matching for very short tokens; the magic-base 2.35 mirrors
    today's logic_v2 behaviour and is one of the spec's still-open
    knobs (see plan § Still open / Length budget shape).
    """
    if not costs:
        return 0.0
    max_cost = math.log(max(len(costs) - 2, 1), 2.35) * fuzzy_tolerance
    total_cost = sum(costs)
    if total_cost == 0:
        return 1.0
    if total_cost > max_cost:
        return 0.0
    return 1 - (total_cost / len(costs))


def _score(cluster: _Cluster, align: _AlignmentData, fuzzy_tolerance: float = DEFAULT_FUZZY_TOLERANCE) -> float:
    """Per-cluster score: product of per-side similarities.

    Solo clusters score 0.0 — they represent unmatched parts and have
    no meaningful pair-based similarity. Punitive product preserves
    today's logic_v2 behaviour (also matches the spec's
    "confidence cliff" requirement; see plan § Score response curve).
    """
    if not cluster.qps or not cluster.rps:
        return 0.0
    qcosts = list(chain.from_iterable(align.qry_costs.get(p, [1.0]) for p in cluster.qps))
    rcosts = list(chain.from_iterable(align.res_costs.get(p, [1.0]) for p in cluster.rps))
    return _costs_similarity(qcosts, fuzzy_tolerance) * _costs_similarity(rcosts, fuzzy_tolerance)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compare_parts_orig(
    qry_parts: List[NamePart],
    res_parts: List[NamePart],
    fuzzy_tolerance: float = DEFAULT_FUZZY_TOLERANCE,
) -> List[Comparison]:
    """Score the alignment of two NamePart lists.

    Inputs are residue parts (post-pruning, post-symbol-pairing,
    already tag-sorted by the caller). Output is one `Comparison`
    per cluster, including solo records for unmatched parts. Every
    input NamePart appears in exactly one `Comparison`.
    """
    align = _align(qry_parts, res_parts)
    clusters = _cluster(qry_parts, res_parts, align)
    return [
        Comparison(qps=list(c.qps), rps=list(c.rps), score=_score(c, align, fuzzy_tolerance))
        for c in clusters
    ]
