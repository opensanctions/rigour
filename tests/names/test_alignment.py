from typing import List
from rigour.names.name import Name
from rigour.names.part import NamePart
from rigour.names.alignment import align_name_slop, align_person_name_order
from rigour.names.tag import NamePartTag


def make(name: str) -> List[NamePart]:
    obj = Name(name, form=name.lower())
    return obj.parts


def test_align_name_slop():
    query = make("Deutsche Bank AG")
    result = make("Deutsche Bank Aktiengesellschaft")
    amt = align_name_slop(query, result, max_slop=2)
    assert amt is not None

    # Example test cases:
    # Deutsche Bank AG vs Deutsche Bank Aktiengesellschaft
    # Deutsche Bank AG vs Deutsche Bahn AG
    # Deutsche Bank (Schweiz) AG vs Deutsche Bank AG
    # Deutsche Bank (Schweiz) AG vs Deutsche Bank Aktiengesellschaft
    # Al-Haramain Foundation vs Al-Haramain Benevolent Foundation
    # Production Enterprise NOVI GAZMASH vs NOVY GAZMASH
    # Production Enterprise NOVI GAZMASH vs NOVIY GASMASH

    # Meant to fail:
    # Deutsche Bank AG vs Bank Deutsch AG
    # NOVY GAZMASH vs GAZMASH NOVY


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

    # TODO:
    # Ali Al-Sabah vs Ali Alsabah
    # Ali Al-Sabah vs Alsabah, Ali
    # Mohammed Abd Al-Rahman vs Abdalrahman, Mohammed


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
