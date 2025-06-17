from typing import List, Optional

from rigour.names.part import NamePart
from rigour.text.distance import levenshtein_similarity, levenshtein


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
            if not qpart.can_match(rpart):
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
        alignment.query_sorted = NamePart.tag_sort(query)
        alignment.result_sorted = NamePart.tag_sort(result)
        return alignment

    for rpart in result:
        if rpart not in alignment.result_sorted:
            alignment.result_extra.append(rpart)

    return alignment


def sausage_press_names(query: List[NamePart], result: List[NamePart]) -> Alignment:
    """Aligns the name parts of a query and result. This is done by incrementally building two
    name prefixes, one for the query and one for the result, with the lowest Levenshtein distance
    between the two prefixes.

    Args:
        query (List[NamePart]): The name parts from the query.
        result (List[NamePart]): The name parts from the result.

    Returns:
        Alignment: An object containing the aligned name parts and any extra parts.
    """
    block_length = 5
    alignment = Alignment()
    if not len(query):
        alignment.result_sorted = result
        return alignment

    query_prefix = query[0].maybe_ascii + ""
    query_left = list(query)
    query_left.remove(query[0])
    alignment.query_sorted.append(query[0])

    result_prefix = ""
    result_left = sorted(result, key=len)

    # Step 1: precise matches
    # for qn, rn in product(query, result):
    #     if qn.can_match(rn) and qn.form == rn.form:
    #         query_aligned.append(qn)
    #         result_aligned.append(rn)
    #         query_prefix += qn.maybe_ascii + ""
    #         result_prefix += rn.maybe_ascii + ""

    while len(query_left) > 0 or len(result_left) > 0:
        # Step 2: find the best match for the next block
        best_score = 0.0
        best_query_part: Optional[NamePart] = None
        best_result_part: Optional[NamePart] = None
        # offset = max(0, min(len(query_prefix), len(result_prefix)) - block_length)

        for rn in result_left:
            if best_score == 1.0:
                # perfect match, no need to check further
                break
            # offset = max(0, len(result_prefix) - block_length)
            # result_next = result_prefix[offset:] + rn.maybe_ascii[:block_length]
            result_next = result_prefix + rn.maybe_ascii[:block_length]
            min_len = max(len(query_prefix), len(result_next))
            distance = levenshtein(query_prefix, result_next, max_edits=min_len * 2)
            score = 1 - (distance / min_len)
            print(
                "result_next:",
                result_next,
                # "offset:",
                # offset,
                "score:",
                score,
                "query_prefix:",
                query_prefix,
            )
            if score >= best_score:
                best_score = score
                best_query_part = None
                best_result_part = rn

        for qn in query_left:
            if best_score == 1.0:
                # perfect match, no need to check further
                break
            # offset = max(0, len(query_prefix) - block_length)
            query_next = query_prefix + qn.maybe_ascii[:block_length]

            min_len = max(len(query_next), len(result_prefix))
            distance = levenshtein(query_next, result_prefix, max_edits=min_len * 2)
            score = 1 - (distance / min_len)
            print(
                "query_next:",
                query_next,
                # "offset:",
                # offset,
                "score:",
                score,
                "result_prefix:",
                result_prefix,
            )
            if score >= best_score:
                best_score = score
                best_query_part = qn
                best_result_part = None

        print(
            "> best score:",
            query_prefix,
            result_prefix,
            best_score,
            best_query_part,
            best_result_part,
        )

        if best_query_part is None and best_result_part is None:
            break

        # Step 3: add the best match to the aligned lists
        if best_query_part is not None:
            alignment.query_sorted.append(best_query_part)
            query_prefix += best_query_part.maybe_ascii + ""
            query_left.remove(best_query_part)
        if best_result_part is not None:
            alignment.result_sorted.append(best_result_part)
            result_prefix += best_result_part.maybe_ascii + ""
            result_left.remove(best_result_part)

    if not len(alignment.query_sorted):
        alignment.query_sorted = NamePart.tag_sort(query)
        alignment.result_sorted = NamePart.tag_sort(result)
        return alignment

    alignment.query_extra.extend(query_left)
    alignment.result_extra.extend(result_left)
    return alignment


if __name__ == "__main__":
    # Example usage
    query_parts = [NamePart("John", 0), NamePart("William", 1), NamePart("Doe", 2)]
    result_parts = [NamePart("Doe", 0), NamePart("John", 1)]
    alignment_sausage = sausage_press_names(query_parts, result_parts)
    print(alignment_sausage)

    query_parts = [NamePart("RamiMakhlouf", 0)]
    result_parts = [NamePart("Rami", 0), NamePart("Makhlouf", 1)]
    alignment_sausage = sausage_press_names(query_parts, result_parts)
    print(alignment_sausage)
