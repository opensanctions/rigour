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
        NamePart("smith", 0, NamePartTag.UNSET),
        NamePart("john", 1, NamePartTag.UNSET),
    ]
    query_sorted, result_sorted = align_person_name_order(query, result)
    assert query_sorted[1].form == result_sorted[1].form
    assert query_sorted[0].form == result_sorted[0].form

    query = [
        NamePart("henry", 1, NamePartTag.GIVEN),
        NamePart("smith", 0, NamePartTag.UNSET),
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


def test_align_deterministic():
    """Running align twice on the same input must produce identical
    output — guards against any hash-map iteration order or other
    non-determinism in the implementation."""
    query = make("Maria Conchita Alonso")
    result = make("Alonso, Maria C.")
    a_left, a_right = align_person_name_order(query, result)
    b_left, b_right = align_person_name_order(make("Maria Conchita Alonso"), make("Alonso, Maria C."))
    assert [p.form for p in a_left] == [p.form for p in b_left]
    assert [p.form for p in a_right] == [p.form for p in b_right]


def test_align_stable_under_ties():
    """With all-UNSET parts and multiple pairs scoring 1.0 (exact
    comparable matches), tie-breaking follows input order:
    longest-first from the length-descending sort, then left-to-right
    across the Cartesian product. Same-length parts tied on score
    must end up in the same output position deterministically."""
    # Two equal-length parts on each side, each matching one-to-one
    # exactly. Any tie-break drift would surface as a swapped order.
    query = make("abcd wxyz")
    result = make("wxyz abcd")
    q1, r1 = align_person_name_order(query, result)
    # Inputs are same length per side; length-descending sort is
    # stable on equal-length elements, so the first-seen-exact-match
    # in the product walk wins. Both sides end up in the same order
    # — whichever one "abcd" landed in first.
    assert [p.form for p in q1] == [p.form for p in r1]
    # And that order is reproducible across runs.
    q2, r2 = align_person_name_order(make("abcd wxyz"), make("wxyz abcd"))
    assert [p.form for p in q1] == [p.form for p in q2]
    assert [p.form for p in r1] == [p.form for p in r2]


def test_align_empty_left():
    """Empty-left short-circuit: returns ([], tag_sort(right))."""
    result = make("John Doe")
    left, right = align_person_name_order([], result)
    assert len(left) == 0
    assert len(right) == 2
    # Right side came through tag_sort — both parts are UNSET so the
    # sort is stable on their input order.
    assert {p.form for p in right} == {"john", "doe"}


def test_align_empty_right():
    """Empty-right case: no pair ever fires, falls back to tag_sort
    on both sides. Left keeps its parts, right stays empty."""
    query = make("John Doe")
    left, right = align_person_name_order(query, [])
    assert len(left) == 2
    assert len(right) == 0
    assert {p.form for p in left} == {"john", "doe"}


def test_align_similarity_floor():
    """Genuinely-different parts should not pair just because the
    greedy loop wants some match — `_name_levenshtein`'s 0.3 floor
    kicks in. With zero-overlap inputs, best_score stays 0.0 and the
    loop breaks immediately, falling through to tag_sort."""
    query = make("John Smith")
    result = make("Xyz Qpr")
    q, r = align_person_name_order(query, result)
    # No pairing → both sides come back tag-sorted rather than
    # interleaved. All parts are UNSET so tag_sort is stable on
    # input order.
    assert len(q) == 2
    assert len(r) == 2
    assert {p.form for p in q} == {"john", "smith"}
    assert {p.form for p in r} == {"xyz", "qpr"}


def test_align_packing_respects_tags():
    """Packing via `_pack_short_parts` gates candidates on
    `NamePartTag.can_match` against the anchor's tag. A candidate
    that would otherwise pack (by string similarity) is excluded if
    its tag is incompatible."""
    # Anchor "alsabah" tagged FAMILY. Candidates are "al" (GIVEN)
    # and "sabah" (FAMILY). Without tags, al+sabah would pack into
    # alsabah; here "al" is skipped because GIVEN doesn't match
    # FAMILY, so alsabah pairs with just sabah, and al stays
    # unmatched at the tail of result_sorted.
    query = [NamePart("alsabah", 0, NamePartTag.FAMILY)]
    result = [
        NamePart("al", 0, NamePartTag.GIVEN),
        NamePart("sabah", 1, NamePartTag.FAMILY),
    ]
    q, r = align_person_name_order(query, result)
    assert len(q) == 1
    assert len(r) == 2
    assert q[0].form == "alsabah"
    # `sabah` pairs with alsabah (aligned index 0); `al` is the
    # unmatched tail.
    assert r[0].form == "sabah"
    assert r[1].form == "al"

    # Control: same surface tokens but all UNSET — packing fires
    # and both `al` and `sabah` get absorbed into the alsabah pair
    # in the order that best matches the anchor ("al" + "sabah" =
    # "alsabah").
    query2 = [NamePart("alsabah", 0)]
    result2 = [NamePart("al", 0), NamePart("sabah", 1)]
    q2, r2 = align_person_name_order(query2, result2)
    assert len(q2) == 1
    assert len(r2) == 2
    assert tokens_eq(r2, ["al", "sabah"])
