from typing import List

from rigour.names.compare import Comparison, compare_parts
from rigour.names.part import NamePart


def parts(*forms: str) -> List[NamePart]:
    return [NamePart(form, i) for i, form in enumerate(forms)]


def test_empty_both_sides() -> None:
    assert compare_parts([], []) == []


def test_empty_one_side_surfaces_solo() -> None:
    qry = parts("vladimir", "putin")
    out = compare_parts(qry, [])
    # Every input part appears in exactly one cluster.
    assert sum(len(c.qps) + len(c.rps) for c in out) == 2
    # All output clusters are solo (one side empty).
    assert all((not c.qps or not c.rps) for c in out)
    # Solo clusters score 0.
    assert all(c.score == 0.0 for c in out)


def test_identical_parts_score_one() -> None:
    qry = parts("vladimir", "putin")
    res = parts("vladimir", "putin")
    out = compare_parts(qry, res)
    assert len(out) == 2
    for comp in out:
        assert len(comp.qps) == 1
        assert len(comp.rps) == 1
        assert comp.score == 1.0


def test_every_input_appears_exactly_once() -> None:
    qry = parts("vladimir", "vladimirovich", "putin")
    res = parts("vladimir", "putin")
    out = compare_parts(qry, res)
    flat_q = [p.form for c in out for p in c.qps]
    flat_r = [p.form for c in out for p in c.rps]
    assert sorted(flat_q) == ["putin", "vladimir", "vladimirovich"]
    assert sorted(flat_r) == ["putin", "vladimir"]


def test_single_fuzzy_edit_keeps_high_score() -> None:
    # "vladimir" vs "vladimer" — one substitute on an 8-char token.
    qry = parts("vladimir")
    res = parts("vladimer")
    out = compare_parts(qry, res)
    assert len(out) == 1
    assert len(out[0].qps) == 1 and len(out[0].rps) == 1
    assert 0.6 < out[0].score < 1.0


def test_budget_cliff_zeroes_cluster() -> None:
    # Same length, more edits than the length-dependent budget allows.
    qry = parts("abcdefgh")
    res = parts("zzzzzzzz")
    out = compare_parts(qry, res)
    # Either one cluster scoring 0 (paired but over budget) or two solo
    # clusters (overlap rule didn't fire). Either way, score is 0.
    assert all(c.score == 0.0 for c in out)


def test_confusable_pair_tier_cheaper_than_default() -> None:
    # "vladimor" vs "vladimer" — one substitute on a confusable pair
    # (`o`/`u` is in the table; let's use one that is). Use "0"/"o" since
    # those are the canonical example.
    confusable_qry = parts("contr0l")  # zero
    confusable_res = parts("control")
    default_qry = parts("contrxl")
    default_res = parts("control")
    confusable_out = compare_parts(confusable_qry, confusable_res)
    default_out = compare_parts(default_qry, default_res)
    # One cluster each, both single-edit on a 7-char token. Confusable
    # tier (0.7) should score strictly higher than default (1.0).
    assert confusable_out[0].score > default_out[0].score


def test_digit_edit_penalty() -> None:
    # Digit-vs-letter substitute on the same token shape — "fund2024" vs
    # "fund2025" should score above the `digit-vs-non-digit` zero floor
    # but below an all-letter substitute of the same edit count, because
    # COST_DIGIT (1.5) is harsher than COST_DEFAULT (1.0).
    digit_out = compare_parts(parts("fund2024"), parts("fund2025"))
    letter_out = compare_parts(parts("fundabcd"), parts("fundabce"))
    # Both single-edit on 8-char tokens; digit edit is more expensive.
    assert digit_out[0].score < letter_out[0].score


def test_fuzzy_tolerance_scales_budget() -> None:
    # A token that fails the cap at default tolerance should pass it
    # at high tolerance, without changing inputs.
    qry = parts("abcdefghij")
    res = parts("zzcdefghzz")
    strict = compare_parts(qry, res, fuzzy_tolerance=0.5)
    permissive = compare_parts(qry, res, fuzzy_tolerance=3.0)
    assert strict[0].score <= permissive[0].score
    # Strict mode should hit the cliff; permissive should pass it.
    assert strict[0].score == 0.0
    assert permissive[0].score > 0.0


def test_short_tokens_disable_fuzzy_match() -> None:
    # 2-char tokens have budget zero — any non-zero edit must fail
    # the cap. Stops the matcher from over-firing on isolated initials,
    # 2-char Chinese given names, vessel hull suffixes.
    out = compare_parts(parts("ab"), parts("ac"))
    assert all(c.score == 0.0 for c in out)


def test_token_merge_is_cheap() -> None:
    # "vanderbilt" vs "van der bilt" — token merge/split is a common
    # surface-form variant; the SEP-drop tier (0.2) should keep the
    # cluster well above zero.
    merged = compare_parts(parts("vanderbilt"), parts("van", "der", "bilt"))
    # Merged side gets one cluster; the alignment binds across the
    # token-split via the cheap SEP-drop tier.
    paired_clusters = [c for c in merged if c.qps and c.rps]
    assert len(paired_clusters) >= 1
    assert all(c.score > 0.5 for c in paired_clusters)


def test_score_is_in_unit_interval() -> None:
    # Across a few shapes, every Comparison's score must be in [0, 1].
    fixtures = [
        (parts("john", "smith"), parts("jon", "smyth")),
        (parts("vladimir"), parts("vladimer")),
        (parts("a"), parts("z")),
        (parts("apple", "banana"), parts("cherry", "date")),
    ]
    for qry, res in fixtures:
        for comp in compare_parts(qry, res):
            assert 0.0 <= comp.score <= 1.0


def test_part_object_identity_preserved() -> None:
    # The Comparison's qps / rps reference the same NamePart objects
    # the caller passed in — callers rely on identity to look back into
    # their own metadata.
    p_qry = NamePart("vladimir", 0)
    p_res = NamePart("vladimir", 0)
    out = compare_parts([p_qry], [p_res])
    assert len(out) == 1
    assert out[0].qps[0] is p_qry
    assert out[0].rps[0] is p_res


def test_repr_shape() -> None:
    out = compare_parts(parts("john"), parts("john"))
    assert len(out) == 1
    r = repr(out[0])
    assert r.startswith("<Comparison(")
    assert "score=" in r


def test_comparison_is_importable_from_public_module() -> None:
    # Productized surface check: both names are reachable from
    # `rigour.names` itself, not just `rigour.names.compare`.
    from rigour.names import Comparison as Top, compare_parts as top_fn

    assert Top is Comparison
    assert top_fn is compare_parts
