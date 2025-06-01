from typing import List, Optional

from rigour.names.part import NamePart
from rigour.names.tag import FAMILY_NAME_TAGS, GIVEN_NAME_TAGS, NamePartTag
from rigour.text.distance import levenshtein_similarity


class Alignment:
    """Data object to hold the alignment of name parts between query and result."""

    def __init__(self) -> None:
        self.query_sorted: List[NamePart] = []
        self.result_sorted: List[NamePart] = []
        self.query_extra: List[NamePart] = []
        self.result_extra: List[NamePart] = []

    def __len__(self) -> int:
        return max(len(self.query_sorted), len(self.result_sorted))


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

    # TODO: the programming
    # see test_alignment.py for examples
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
    if len(query) < 2 or len(result) < 2:
        alignment.query_sorted = query
        alignment.result_sorted = result
        return alignment

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
        alignment.result_sorted = result
        return alignment

    for rpart in result:
        if rpart not in alignment.result_sorted:
            alignment.result_extra.append(rpart)

    return alignment
