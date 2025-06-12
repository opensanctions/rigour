from typing import List, Optional

from rigour.names.part import NamePart
from rigour.names.tag import FAMILY_NAME_TAGS, GIVEN_NAME_TAGS, NamePartTag
from rigour.text.distance import levenshtein_similarity


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


def align_name_slop(
    query: List[NamePart], result: List[NamePart], max_slop: int = 2
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
    if len(query) < 2 or len(result) < 2:
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
            # no alignment found, skip both
            alignment.query_extra.append(query[query_index])
            alignment.result_extra.append(result[result_index])
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
    # add any remaining parts to extra
    alignment.query_extra.extend(query[query_index:])
    alignment.result_extra.extend(result[result_index:])

    return alignment


def _check_align_tags(query: NamePart, result: NamePart) -> bool:
    """
    Check if the tags of the query and result name parts can be aligned.

    Args:
        query (NamePart): The name part from the query.
        result (NamePart): The name part from the result.

    Returns:
        bool: True if the tags can be aligned, False otherwise.
    """
    if NamePartTag.ANY in (query.tag, result.tag):
        return True
    if query.tag in GIVEN_NAME_TAGS and result.tag in FAMILY_NAME_TAGS:
        return False
    if query.tag in FAMILY_NAME_TAGS and result.tag in GIVEN_NAME_TAGS:
        return False
    return True


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

    for qpart in sorted(query, key=len, reverse=True):
        best_match: Optional[NamePart] = None
        best_score = 0.0
        for rpart in sorted(result, key=len, reverse=True):
            if rpart in alignment.result_sorted:
                continue
            if not _check_align_tags(qpart, rpart):
                continue
            min_len = min(len(qpart.maybe_ascii), len(rpart.maybe_ascii))
            score = levenshtein_similarity(
                qpart.maybe_ascii,
                rpart.maybe_ascii,
                max_edits=min_len // 2,
                max_percent=1.0,
            )
            score = score * min_len
            if score > best_score:
                best_score = score
                best_match = rpart

        if best_match is not None:
            alignment.query_sorted.append(qpart)
            alignment.result_sorted.append(best_match)
        else:
            alignment.query_extra.append(qpart)

    if not len(alignment.query_sorted):
        alignment.query_sorted = query
        alignment.result_extra = result
        return alignment

    for rpart in result:
        if rpart not in alignment.result_sorted:
            alignment.result_extra.append(rpart)

    return alignment
