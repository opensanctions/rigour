from typing import List
from rigour.names.name import Name
from rigour.names.part import NamePart
from rigour.names.alignment import align_person_name_order
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


def test_align_person_name_order():
    query = make("John Doe")
    result = make("Doe, John")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert len(result_sorted) == 2
    assert tokens_eq(query_sorted, ["john", "doe"])
    assert tokens_eq(result_sorted, ["john", "doe"])

    query = make("John Dow")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert tokens_eq(query_sorted, ["john", "dow"])
    assert tokens_eq(result_sorted, ["john", "doe"])

    query = make("John Richard Smith")
    result = make("Smith, John")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 3
    assert tokens_eq(query_sorted, ["smith", "john", "richard"])

    query = make("John Richard Smyth")
    result = make("Smith, John")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 3
    assert tokens_eq(result_sorted, ["john", "smith"])
    assert tokens_eq(query_sorted, ["john", "smyth", "richard"])

    query = make("Vladimir Vladimirovitch Putin")
    result = make("Vladimir Putin")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 3
    assert tokens_eq(query_sorted, ["vladimir", "putin", "vladimirovitch"])

    query = make("Vladimir Vladimirovitch Putin")
    result = make("Vladimir Pudin")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 3
    assert tokens_eq(query_sorted, ["vladimir", "putin", "vladimirovitch"])

    query = make("Vladimir Putin")
    result = make("Vladimir Vladimirovitch Putin")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert tokens_eq(result_sorted, ["vladimir", "putin", "vladimirovitch"])


def test_name_packing():
    query = make("Ali Al-Sabah")
    result = make("Alsabah, Ali")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 3
    assert len(result_sorted) == 2
    assert tokens_eq(query_sorted, ["ali", "al", "sabah"])
    assert tokens_eq(result_sorted, ["ali", "alsabah"])

    query = make("Mohammed Abd Al-Rahman")
    result = make("Abdalrahman, Mohammed")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 4
    assert len(result_sorted) == 2

    query = make("RamiMakhlouf")
    result = make("Maklouf, Ramy")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 1
    assert len(result_sorted) == 2
    assert tokens_eq(result_sorted, ["ramy", "maklouf"])

    query = make("AlisherUsmanov")
    result = make("Alisher Usmanov")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 1
    assert len(result_sorted) == 2

    query = make("Alisher Usmanov")
    result = make("AlisherUsmanov")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert len(result_sorted) == 1
    assert tokens_eq(query_sorted, ["alisher", "usmanov"])

    query = make("Usmanov Alisher")
    result = make("AlisherUsmanov")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert len(result_sorted) == 1
    assert tokens_eq(query_sorted, ["alisher", "usmanov"])


def test_align_person_special_cases():
    query = make("John")
    result = make("Doe")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 1
    assert len(result_sorted) == 1

    query_sorted, result_sorted = align_person_name_order([], [])
    assert len(query_sorted) == 0
    assert len(result_sorted) == 0

    query = make("Sergei Ivanovich")
    result = make("Sergei")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert len(result_sorted) == 1

    query = make("Sergei")
    result = make("Sergei Ivanovich")
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 1
    assert len(result_sorted) == 2


def test_align_tagged_person_name_parts():
    query = [
        NamePart("john", 0, NamePartTag.GIVEN),
        NamePart("smith", 1, NamePartTag.FAMILY),
    ]
    result = [
        NamePart("john", 0, NamePartTag.GIVEN),
        NamePart("smith", 1, NamePartTag.FAMILY),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert len(result_sorted) == 2
    assert query_sorted[1].form == "john"
    assert result_sorted[1].form == "john"
    assert query_sorted[0].form == "smith"
    assert result_sorted[0].form == "smith"
    query = [
        NamePart("smith", 0, NamePartTag.FAMILY),
        NamePart("john", 1, NamePartTag.GIVEN),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert query_sorted[0].form == result_sorted[0].form

    query = [
        NamePart("smith", 0, NamePartTag.ANY),
        NamePart("john", 1, NamePartTag.ANY),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert query_sorted[1].form == result_sorted[1].form
    assert query_sorted[0].form == result_sorted[0].form

    query = [
        NamePart("henry", 1, NamePartTag.GIVEN),
        NamePart("smith", 0, NamePartTag.ANY),
        NamePart("john", 1, NamePartTag.GIVEN),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 3
    assert query_sorted[2].form == "henry"

    query = [
        NamePart("smith", 0, NamePartTag.GIVEN),
        NamePart("john", 1, NamePartTag.FAMILY),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert len(query_sorted) == 2
    assert len(result_sorted) == 2
    assert query_sorted[0].form != result_sorted[0].form
    assert query_sorted[1].form != result_sorted[1].form

    query = [
        NamePart("hans", 0, NamePartTag.GIVEN),
        NamePart("friedrich", 1, NamePartTag.FAMILY),
    ]
    result = [
        NamePart("hans", 0, NamePartTag.FAMILY),
        NamePart("friedrich", 1, NamePartTag.GIVEN),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert query_sorted[0].form == "hans"
    assert query_sorted[1].form == "friedrich"
    assert result_sorted[0].form == "friedrich"
    assert result_sorted[1].form == "hans"
