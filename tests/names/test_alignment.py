from typing import List
from rigour.names.name import Name
from rigour.names.part import NamePart
from rigour.names.alignment import align_name_slop, align_person_name_order
from rigour.names.tag import NamePartTag


def make(name: str) -> List[NamePart]:
    obj = Name(name, form=name.lower())
    return obj.parts


def tokens_eq(a: List[NamePart], b: List[str]) -> bool:
    if len(a) != len(b):
        return False
    for i, part in enumerate(a):
        if part.form != b[i]:
            return False
    return True


def test_align_name_slop():
    # Extra
    query = make("Deutsche Bank AG")
    result = make("Deutsche Bank Aktiengesellschaft")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["deutsche", "bank"])
    assert tokens_eq(amt.result_sorted, ["deutsche", "bank"])
    assert tokens_eq(amt.query_extra, ["ag"])
    assert tokens_eq(amt.result_extra, ["aktiengesellschaft"])

    # Fuzzy
    query = make("Deutsche Bank AG")
    result = make("Deutsche Bahn AG")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["deutsche", "bank", "ag"])
    assert tokens_eq(amt.result_sorted, ["deutsche", "bahn", "ag"])
    assert tokens_eq(amt.query_extra, [])
    assert tokens_eq(amt.result_extra, [])

    # Extra in the middle of query
    query = make("Deutsche Bank (Schweiz) AG")
    result = make("Deutsche Bank AG")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["deutsche", "bank", "ag"])
    assert tokens_eq(amt.result_sorted, ["deutsche", "bank", "ag"])
    assert tokens_eq(amt.query_extra, ["schweiz"])
    assert tokens_eq(amt.result_extra, [])

    # Multiple extra
    query = make("Deutsche Bank (Schweiz) AG")
    result = make("Deutsche Bank Aktiengesellschaft")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["deutsche", "bank"])
    assert tokens_eq(amt.result_sorted, ["deutsche", "bank"])
    assert tokens_eq(amt.query_extra, ["schweiz", "ag"])
    assert tokens_eq(amt.result_extra, ["aktiengesellschaft"])

    # Extra in the middle of result
    query = make("Al-Haramain Foundation")
    result = make("Al-Haramain Benevolent Foundation")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["al", "haramain", "foundation"])
    assert tokens_eq(amt.result_sorted, ["al", "haramain", "foundation"])
    assert tokens_eq(amt.query_extra, [])
    assert tokens_eq(amt.result_extra, ["benevolent"])

    # Extra at the start of query, fuzzy
    query = make("Production Enterprise NOVI GAZMASH")
    result = make("NOVY GAZMASH")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["novi", "gazmash"])
    assert tokens_eq(amt.result_sorted, ["novy", "gazmash"])
    assert tokens_eq(amt.query_extra, ["production", "enterprise"])
    assert tokens_eq(amt.result_extra, [])

    # Extra at the start of result, fuzzy
    query = make("NOVI GAZMASH")
    result = make("Production Enterprise NOVIY GASMASH")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["novi", "gazmash"])
    assert tokens_eq(amt.result_sorted, ["noviy", "gasmash"])
    assert tokens_eq(amt.query_extra, [])
    assert tokens_eq(amt.result_extra, ["production", "enterprise"])

    # While goo is within slop, we can't reorder to align it
    query = make("Goo Blue Flowers")
    result = make("Blue Flowers Goo")
    amt = align_name_slop(query, result, max_slop=2)
    assert tokens_eq(amt.query_sorted, ["blue", "flowers"])
    assert tokens_eq(amt.result_sorted, ["blue", "flowers"])
    assert tokens_eq(amt.query_extra, ["goo"])
    assert tokens_eq(amt.result_extra, ["goo"])

    # NOVY GAZMASH vs GAZMASH NOVY
    query = make("NOVY GAZMASH")
    result = make("GAZMASH NOVY")
    amt = align_name_slop(query, result, max_slop=2)
    # Both keeping GAZMASH is better because it's longer
    # but perhaps either is valid and that can be an enhancement
    assert tokens_eq(amt.query_sorted, ["novy"])
    assert tokens_eq(amt.result_sorted, ["novy"])
    assert tokens_eq(amt.query_extra, ["gazmash"])
    assert tokens_eq(amt.result_extra, ["gazmash"])


def test_align_slop_special_cases():
    query = make("Bank")
    result = make("Kling")
    amt = align_name_slop(query, result)
    assert len(amt.query_sorted) == 1
    assert len(amt.result_sorted) == 1

    amt = align_name_slop([], [])
    assert len(amt.query_sorted) == 0
    assert len(amt.result_sorted) == 0


def test_align_person_name_order():
    query = make("John Doe")
    result = make("Doe, John")
    amt = align_person_name_order(query, result)
    assert len(amt.query_sorted) == 2
    assert len(amt.result_sorted) == 2
    assert amt.query_sorted[0].form == "john"
    assert amt.query_sorted[1].form == "doe"
    assert amt.result_sorted[0].form == "john"
    assert amt.result_sorted[1].form == "doe"

    query = make("John Dow")
    amt = align_person_name_order(query, result)
    assert len(amt.query_sorted) == 2
    assert amt.query_sorted[0].form == "john"
    assert amt.query_sorted[1].form == "dow"
    assert amt.result_sorted[0].form == "john"
    assert amt.result_sorted[1].form == "doe"

    query = make("John Richard Smith")
    result = make("Smith, John")
    amt = align_person_name_order(query, result)

    assert len(amt.query_sorted) == 2
    assert amt.query_sorted[0].form == "smith"
    assert amt.query_sorted[1].form == "john"
    assert amt.query_extra[0].form == "richard"
    assert amt.result_sorted[0].form == "smith"
    assert amt.result_sorted[1].form == "john"

    query = make("John Richard Smyth")
    amt = align_person_name_order(query, result)

    assert len(amt.query_sorted) == 2
    assert amt.query_sorted[0].form == "smyth"
    assert amt.query_sorted[1].form == "john"
    assert amt.query_extra[0].form == "richard"

    query = make("Vladimir Vladimirovitch Putin")
    result = make("Vladimir Putin")
    amt = align_person_name_order(query, result)
    assert len(amt.query_sorted) == 2
    assert amt.query_sorted[0].form == "vladimir"
    assert amt.query_extra[0].form == "vladimirovitch"

    query = make("Vladimir Putin")
    result = make("Vladimir Vladimirovitch Putin")
    amt = align_person_name_order(query, result)
    assert len(amt.query_sorted) == 2
    assert amt.result_sorted[0].form == "vladimir"
    assert amt.result_extra[0].form == "vladimirovitch"

    # TODO:
    # Ali Al-Sabah vs Ali Alsabah
    # Ali Al-Sabah vs Alsabah, Ali
    # Mohammed Abd Al-Rahman vs Abdalrahman, Mohammed


def test_align_person_special_cases():
    query = make("John")
    result = make("Doe")
    amt = align_person_name_order(query, result)
    assert len(amt.query_sorted) == 1
    assert len(amt.result_sorted) == 1

    amt = align_person_name_order([], [])
    assert len(amt.query_sorted) == 0
    assert len(amt.result_sorted) == 0


def test_align_tagged_person_name_parts():
    query = [
        NamePart("john", 0, NamePartTag.GIVEN),
        NamePart("smith", 1, NamePartTag.FAMILY),
    ]
    result = [
        NamePart("john", 0, NamePartTag.GIVEN),
        NamePart("smith", 1, NamePartTag.FAMILY),
    ]
    aligned = align_person_name_order(query, result)
    assert len(aligned) == 2
    assert aligned.query_sorted[1].form == "john"
    assert aligned.result_sorted[1].form == "john"
    assert aligned.query_sorted[0].form == "smith"
    assert aligned.result_sorted[0].form == "smith"
    query = [
        NamePart("smith", 0, NamePartTag.FAMILY),
        NamePart("john", 1, NamePartTag.GIVEN),
    ]
    aligned = align_person_name_order(query, result)
    assert len(aligned) == 2, (aligned.query_sorted, aligned.result_sorted)
    assert aligned.query_sorted[0].form == aligned.result_sorted[0].form

    query = [
        NamePart("smith", 0, NamePartTag.ANY),
        NamePart("john", 1, NamePartTag.ANY),
    ]
    aligned = align_person_name_order(query, result)
    assert len(aligned) == 2
    assert aligned.query_sorted[1].form == aligned.result_sorted[1].form
    assert aligned.query_sorted[0].form == aligned.result_sorted[0].form

    query = [
        NamePart("henry", 1, NamePartTag.GIVEN),
        NamePart("smith", 0, NamePartTag.ANY),
        NamePart("john", 1, NamePartTag.GIVEN),
    ]
    aligned = align_person_name_order(query, result)
    assert len(aligned) == 2
    assert len(aligned.query_extra) == 1

    query = [
        NamePart("smith", 0, NamePartTag.GIVEN),
        NamePart("john", 1, NamePartTag.FAMILY),
    ]
    aligned = align_person_name_order(query, result)
    assert len(aligned) == 2, (aligned.query_sorted, aligned.result_sorted)
    assert aligned.query_sorted[0].form != aligned.result_sorted[0].form
    assert aligned.query_sorted[1].form != aligned.result_sorted[1].form
