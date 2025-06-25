from itertools import product
from typing import List, Optional

from rigour.names.part import NamePart
from rigour.text.distance import levenshtein_similarity, dam_levenshtein


MAX_EDITS = 4
MAX_PERCENT = 0.5
MIN_SIMILARITY = 0.5


class Alignment:
    """Data object to hold the alignment of name parts between query and result."""

    def __init__(self) -> None:
        self.query_sorted: List[NamePart] = []
        self.result_sorted: List[NamePart] = []
        self.query_extra: List[NamePart] = []
        self.result_extra: List[NamePart] = []

    def __len__(self) -> int:
        return max(len(self.query_sorted), len(self.result_sorted))

    def __repr__(self) -> str:
        return f"<Alignment({self.query_sorted!r} <> {self.result_sorted!r}, qe={self.query_extra!r}, re={self.result_extra!r})>"


class Pair:
    """A pair of name parts from query and result."""

    def __init__(self, left: NamePart, right: NamePart, score: float) -> None:
        self.left = left
        self.right = right
        self.score = score

    def __repr__(self) -> str:
        return f"Pair(left={self.left}, result={self.right}, score={self.right})"


def check_similarity(left: NamePart, right: NamePart) -> Optional[Pair]:
    score = levenshtein_similarity(left.form, right.form, MAX_EDITS, MAX_PERCENT)
    if score >= MIN_SIMILARITY:
        return Pair(left=left, right=right, score=score)
    return None


def best_alignment(
    part: NamePart, candidates: List[NamePart], swap: bool = False
) -> Optional[Pair]:
    pairs: List[Pair] = []
    num = len(candidates)
    for i, candidate in enumerate(candidates):
        slop_penalty = (num - i) / num
        pair = check_similarity(part, candidate)
        if pair is not None:
            pair.score = pair.score * slop_penalty
            pairs.append(pair)
    maximal = max(pairs, key=lambda p: p.score, default=None)
    if swap and maximal is not None:
        return Pair(left=maximal.right, right=maximal.left, score=maximal.score)
    return maximal


def align_tag_sort(query: List[NamePart], result: List[NamePart]) -> Alignment:
    """Align name parts of companies and organizations by sorting them by their tags.
    This is a simple alignment that does not allow for any slop or re-ordering of name
    parts, but it is useful for cases where the names are already well-formed and
    comparable.

    Args:
        query (List[NamePart]): The name parts of the query.
        result (List[NamePart]): The name parts of the result.
    Returns:
        Alignment: An object containing the aligned name parts and any extra parts.
    """
    alignment = Alignment()
    alignment.query_sorted = NamePart.tag_sort(query)
    alignment.result_sorted = NamePart.tag_sort(result)
    return alignment


def align_name_slop(
    query: List[NamePart],
    result: List[NamePart],
    max_slop: int = 2,
) -> Alignment:
    """Align name parts of companies and organizations. The idea here is to allow
    skipping tokens within the entity name if this improves overall match quality,
    but never to re-order name parts. The resulting alignment will contain the
    sorted name parts of both the query and the result, as well as any extra parts
    that were not aligned.

    Note that one name part in one list may correspond to multiple name parts in the
    other list, so the alignment is not necessarily one-to-one.

    The `levenshtein` distance is used to determine the best alignment, allowing
    for a certain spelling variation between the names.

    Args:
        query (List[NamePart]): The name parts of the query.
        result (List[NamePart]): The name parts of the result.
        max_slop (int): The maximum number of tokens that can be skipped in the
            alignment. Defaults to 2.
    Returns:
        Alignment: An object containing the aligned name parts and any extra parts.
    """
    alignment = Alignment()
    if len(query) < 2 and len(result) < 2:
        alignment.query_sorted = query
        alignment.result_sorted = result
        return alignment

    query_index = 0
    result_index = 0
    while query_index < len(query) and result_index < len(result):
        # get the best alignment of query to result
        query_best = best_alignment(
            query[query_index], result[result_index : result_index + max_slop + 1]
        )
        # get the best alignment of result to query
        result_best = best_alignment(
            result[result_index],
            query[query_index : query_index + max_slop + 1],
            swap=True,
        )
        # take the best of both
        if query_best is None and result_best is None:
            # No alignment found within slop, move forward with bad alignment
            # unless we are at the end of either list.
            if query_index == len(query) - 1 or result_index == len(result) - 1:
                break
            alignment.query_sorted.append(query[query_index])
            alignment.result_sorted.append(result[result_index])
            query_index += 1
            result_index += 1
            continue
        elif query_best is not None and result_best is not None:
            if query_best.score >= result_best.score:
                best = query_best
            else:
                best = result_best
        elif query_best is not None:
            best = query_best
        elif result_best is not None:
            best = result_best
        else:
            raise ValueError("Shouldn't reach here.")
        # add the best alignment to the Alignment
        alignment.query_sorted.append(best.left)
        alignment.result_sorted.append(best.right)
        # if we skip any, add them to extra
        assert best.left.index is not None, best.left
        assert best.right.index is not None, best.right
        alignment.query_extra.extend(query[query_index : best.left.index])
        alignment.result_extra.extend(result[result_index : best.right.index])
        # move to the step after the aligned parts
        query_index = best.left.index + 1
        result_index = best.right.index + 1
    # Add slop remaining parts to extra and the rest to sorted.
    # We do this because max_slop parts are allowed to be ignored, but anything
    # beyond that should penalise any similarity comparison on the sorted parts.
    alignment.query_extra.extend(query[query_index : query_index + max_slop])
    alignment.query_sorted.extend(query[query_index + max_slop :])
    alignment.result_extra.extend(result[result_index : result_index + max_slop])
    alignment.result_sorted.extend(result[result_index + max_slop :])
    return alignment


def align_name_strict(
    query: List[NamePart], result: List[NamePart], max_slop: int = 2
) -> Alignment:
    """Align name parts of companies and organizations strictly by their token sequence. This
    implementation does not use fuzzy matching or Levenshtein distance, but rather aligns
    names only if individual name parts match exactly.

    Args:
        query (List[NamePart]): The name parts of the query.
        result (List[NamePart]): The name parts of the result.
    Returns:
        Alignment: An object containing the aligned name parts and any extra parts.
    """
    alignment = Alignment()
    if len(query) < 2 or len(result) < 2:
        alignment.query_sorted = query
        alignment.result_sorted = result
        return alignment
    query = NamePart.tag_sort(query)
    result = NamePart.tag_sort(result)
    query_offset = 0
    result_offset = 0
    while True:
        if query_offset >= len(query) or result_offset >= len(result):
            break
        slop_used = len(alignment.query_extra) + len(alignment.result_extra)
        slop_remaining = max(0, max_slop - slop_used)
        for i in range(slop_remaining + 1):
            query_next = query_offset + i
            if query_next < len(query):
                query_part = query[query_next]
                if query_part.comparable == result[result_offset].comparable:
                    alignment.query_sorted.append(query_part)
                    alignment.result_sorted.append(result[result_offset])
                    alignment.query_extra.extend(query[query_offset:query_next])
                    query_offset += i
                    break
            result_next = result_offset + i
            if result_next < len(result):
                result_part = result[result_next]
                if result_part.comparable == query[query_offset].comparable:
                    alignment.query_sorted.append(query[query_offset])
                    alignment.result_sorted.append(result_part)
                    alignment.result_extra.extend(result[result_offset:result_next])
                    result_offset += i
                    break

        query_offset += 1
        result_offset += 1

    # Add any remaining parts to extra and the rest to sorted.
    alignment.query_sorted.extend(query[query_offset:])
    alignment.result_sorted.extend(result[result_offset:])
    return alignment


def _name_levenshtein(query: List[NamePart], result: List[NamePart]) -> float:
    query_str = "".join([p.comparable for p in query])
    result_str = "".join([p.comparable for p in result])
    max_len = max(len(query_str), len(result_str))
    if query_str == result_str or max_len == 0:
        return 1.0
    distance = dam_levenshtein(query_str, result_str)
    score = 1 - (distance / max_len)
    if score < 0.3:
        return 0.0
    return score


def _pack_short_parts(
    part: NamePart, other: NamePart, options: List[NamePart]
) -> List[NamePart]:
    packed: List[NamePart] = [other]
    for op in options:
        if op in packed:
            continue
        if not part.can_match(op):
            continue
        base_str = "".join([p.comparable for p in packed])
        if len(base_str) >= len(part.form):
            break
        best_score = _name_levenshtein([part], packed)
        best_packed = None
        for i in range(len(packed) + 1):
            next_packed = packed.copy()
            next_packed.insert(i, op)
            next_score = _name_levenshtein([part], next_packed)
            if next_score > best_score:
                best_score = next_score
                best_packed = next_packed
        if best_packed is not None:
            packed = best_packed
    return packed


def align_person_name_order(query: List[NamePart], result: List[NamePart]) -> Alignment:
    """Aligns the name parts of a person name for the query and result based on their
    tags and their string similarity such that the most similar name parts are matched.

    Args:
        query (List[NamePart]): The name parts from the query.
        result (List[NamePart]): The name parts from the result.

    Returns:
        Alignment: An object containing the aligned name parts and any extra parts.
    """
    alignment = Alignment()
    if not len(query):
        alignment.result_sorted = result
        return alignment

    query_left = sorted(query, key=len, reverse=True)
    result_left = sorted(result, key=len, reverse=True)
    while len(query_left) > 0 and len(result_left) > 0:
        best_score = 0.0
        best_query_parts: Optional[List[NamePart]] = None
        best_result_parts: Optional[List[NamePart]] = None
        for qp, rp in product(query_left, result_left):
            if not qp.can_match(rp):
                continue
            if qp.comparable == rp.comparable:
                best_score = 1.0
                best_query_parts = [qp]
                best_result_parts = [rp]
                break
            # check the Levenshtein distance between the two parts
            score = _name_levenshtein([qp], [rp])
            if score > best_score:
                best_query_parts = [qp]
                best_result_parts = [rp]
                if len(qp.form) > len(rp.form):
                    best_result_parts = _pack_short_parts(qp, rp, result_left)
                elif len(rp.form) > len(qp.form):
                    best_query_parts = _pack_short_parts(rp, qp, query_left)
                best_score = _name_levenshtein(best_query_parts, best_result_parts)

        if best_score == 0.0:
            # no match found, break out of the loop
            break

        if best_query_parts is not None:
            alignment.query_sorted.extend(best_query_parts)
            for qp in best_query_parts:
                query_left.remove(qp)
        if best_result_parts is not None:
            alignment.result_sorted.extend(best_result_parts)
            for rp in best_result_parts:
                result_left.remove(rp)

    if not len(alignment.query_sorted):
        return align_tag_sort(query, result)

    alignment.query_extra.extend(query_left)
    alignment.result_extra.extend(result_left)
    return alignment
