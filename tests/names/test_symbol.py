"""Tests for rigour.names.symbol.pair_symbols.

House style mirrors tests/names/test_analyze.py — one concept per
test, assertions on the pairing shape rather than object identity.

Inputs come through `analyze_names` so the real person and
organisation name corpora drive the tagger. Tests marked
`# corpus-dependent` rely on specific entries in those corpora and
may need their inputs retuned if the data shifts.
"""

from typing import List, Tuple

from rigour.names import (
    Name,
    NamePartTag,
    NameTypeTag,
    Symbol,
    analyze_names,
)
from rigour.names.symbol import SymbolEdge, pair_symbols


def _only(names: "set[Name]") -> Name:
    """Extract the single Name from a size-1 result set."""
    assert len(names) == 1, f"expected 1 Name, got {len(names)}: {names}"
    return next(iter(names))


def pair_shape(
    pairings: List[Tuple[SymbolEdge, ...]],
) -> List[List[Tuple[str, str, str]]]:
    """Normalise pairings for readable pytest diffs.

    Each pairing becomes a sorted `list` of `(query_text,
    result_text, category)` tuples. Text fields are space-joined
    `part.form` so assertions read like the input names; sorting
    makes the comparison order-free while preserving multiplicity
    — a single pairing can legitimately carry two identical edges
    (same symbol occurring twice on both sides).
    """
    return [
        sorted(
            (
                " ".join(p.form for p in e.query_parts),
                " ".join(p.form for p in e.result_parts),
                e.symbol.category.value,
            )
            for e in edges
        )
        for edges in pairings
    ]


# --- degenerate cases ---


def test_no_shared_symbols():
    # Different person names → no shared symbols → one empty pairing.
    q = _only(analyze_names(NameTypeTag.PER, ["John"]))
    r = _only(analyze_names(NameTypeTag.PER, ["Mary"]))
    assert pair_shape(pair_symbols(q, r)) == [[]]


def test_no_symbols_at_all():
    # Neither name carries any tagger-emitted symbol (tokens aren't
    # in the person-names or generic-symbol corpora). The candidate
    # edge set is empty, but pair_symbols must still return one
    # empty pairing so the downstream scoring loop runs and full
    # Levenshtein gets computed on the remainder.
    q = _only(analyze_names(NameTypeTag.PER, ["zzfoo zzbar"]))
    r = _only(analyze_names(NameTypeTag.PER, ["zzbaz zzqux"]))
    assert not q.symbols
    assert not r.symbols
    assert pair_shape(pair_symbols(q, r)) == [[]]


def test_empty_query():
    # Pairing against an empty-form Name yields a single empty pairing.
    r = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    empty = Name("", tag=NameTypeTag.PER)
    assert pair_shape(pair_symbols(empty, r)) == [set()]


# --- person-name cases ---


def test_identical_person():
    q = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    r = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [("john", "john", "NAME"), ("smith", "smith", "NAME")],
    ]


def test_person_reorder():
    # Word order doesn't change the covering.
    q = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    r = _only(analyze_names(NameTypeTag.PER, ["Smith John"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [("john", "john", "NAME"), ("smith", "smith", "NAME")],
    ]


def test_partial_overlap_with_remainder():
    # Middle name has no symbol — left for downstream remainder
    # scoring, not covered by a pairing edge.
    q = _only(analyze_names(NameTypeTag.PER, ["John Michael Smith"]))
    r = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [("john", "john", "NAME"), ("smith", "smith", "NAME")],
    ]


def test_initial_pairs_with_full_given():
    # `J` with INITIAL:j pairs against `John` when John also carries
    # INITIAL:j on the result side.
    q = _only(analyze_names(NameTypeTag.PER, ["J Smith"], infer_initials=True))
    r = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [("j", "john", "INITIAL"), ("smith", "smith", "NAME")],
    ]


def test_initial_rejected_when_both_multichar():
    # Both sides carry INITIAL symbols on multi-character parts — the
    # per-edge compatibility rule rejects the edge, leaving only the
    # NAME edges in the covering.
    q = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    r = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    shape = pair_shape(pair_symbols(q, r))
    for pairing in shape:
        assert not any(cat == "INITIAL" for _, _, cat in pairing)


def test_given_family_tag_mismatch():
    # Same NAME symbols on both sides, but part_tags make them
    # incompatible under NamePartTag.can_match → edges rejected.
    q = _only(
        analyze_names(
            NameTypeTag.PER,
            ["John Smith"],
            {NamePartTag.GIVEN: ["John"], NamePartTag.FAMILY: ["Smith"]},
        )
    )
    r = _only(
        analyze_names(
            NameTypeTag.PER,
            ["John Smith"],
            {NamePartTag.FAMILY: ["John"], NamePartTag.GIVEN: ["Smith"]},
        )
    )
    shape = pair_shape(pair_symbols(q, r))
    for pairing in shape:
        assert ("john", "john", "NAME") not in pairing
        assert ("smith", "smith", "NAME") not in pairing


# --- multi-part alignment ---


def test_symbol_different_span_lengths():  # corpus-dependent
    # "abd al-kadir" (3 tokens, one NAME span) and "abdelkader"
    # (1 token, same NAME symbol). Single edge pairs the 3-part
    # qspan with the 1-part rspan; "husseini" pairs separately.
    q = _only(analyze_names(NameTypeTag.PER, ["abd al-kadir husseini"]))
    r = _only(analyze_names(NameTypeTag.PER, ["abdelkader husseini"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [
            ("abd al kadir", "abdelkader", "NAME"),
            ("husseini", "husseini", "NAME"),
        ],
    ]


def test_symbol_twice_on_one_side():  # corpus-dependent
    # Two query-side spans for the same NAME symbol, one result-side
    # span: N=2, M=1, bind min(N, M)=1 pair. Single pairing; the
    # unbound query span lands in the downstream remainder.
    # Intra-symbol binding is greedy by span-index order, so the
    # first qspan ("abd al kadir") wins and "abdel kader" stays
    # unaligned.
    q = _only(
        analyze_names(NameTypeTag.PER, ["abd al-kadir abdel-kader husseini"])
    )
    r = _only(analyze_names(NameTypeTag.PER, ["abdelkader husseini"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [
            ("abd al kadir", "abdelkader", "NAME"),
            ("husseini", "husseini", "NAME"),
        ],
    ]


def test_symbol_twice_on_both_sides():  # corpus-dependent
    # Same NAME symbol twice on each side: N=M=2, bind two edges
    # within one pairing (not two alternative pairings). The
    # instances are interchangeable for downstream scoring.
    q = _only(analyze_names(NameTypeTag.PER, ["John John Smith"]))
    r = _only(analyze_names(NameTypeTag.PER, ["John John Smith"]))
    shape = pair_shape(pair_symbols(q, r))
    assert len(shape) == 1
    pairing = shape[0]
    john_edges = [e for e in pairing if e[0] == "john" and e[1] == "john"]
    assert len(john_edges) == 2
    smith_edges = [e for e in pairing if e[0] == "smith" and e[1] == "smith"]
    assert len(smith_edges) == 1


# --- multi-category on the same part ---


def test_same_part_multiple_categories():  # corpus-dependent
    # A token can carry symbols in more than one category. Dutch
    # nobiliary "van" sits in both the person-names corpus (NAME)
    # and the generic-qualifier list (SYMBOL). When the token
    # appears on both sides carrying both categories, two pairings
    # surface — same query/result coverage, distinct category
    # multiset, therefore distinct downstream SYM_SCORES/SYM_WEIGHTS.
    # Each individual pairing picks one of the two categories for
    # van↔van because the two candidate edges share the same parts
    # and so conflict.
    #
    # `van Putin` is deliberately not a stored compound — "van Dijk"
    # or "van der Berg" would trigger a multi-part NAME symbol that
    # subsumes the one-part `van` edge and muddies what we're
    # testing. Using an invented combination keeps only the
    # cross-category case on the `van` token itself.
    q = _only(analyze_names(NameTypeTag.PER, ["van Putin"]))
    r = _only(analyze_names(NameTypeTag.PER, ["van Putin"]))
    shape = pair_shape(pair_symbols(q, r))
    van_categories = set()
    for pairing in shape:
        for qtext, rtext, cat in pairing:
            if qtext == "van" and rtext == "van":
                van_categories.add(cat)
    assert "NAME" in van_categories
    assert "SYMBOL" in van_categories


# --- same-category subsumption ---


def test_same_category_subsumption():  # corpus-dependent
    # "van Dijk" is a compound NAME symbol in the person-names
    # corpus. "van" and "Dijk" may also be tagged as standalone
    # NAME symbols. When the compound spans both sides, it
    # strictly dominates the masks of the shorter same-category
    # edges — and the shorter NAME edges get pruned before the
    # coverage DFS runs. Cross-category edges (SYMBOL:van) are
    # unaffected by the prune.
    q = _only(analyze_names(NameTypeTag.PER, ["Jan van Dijk"]))
    r = _only(analyze_names(NameTypeTag.PER, ["Jan van Dijk"]))
    shape = pair_shape(pair_symbols(q, r))
    # The compound NAME edge surfaces in at least one pairing.
    assert any(
        ("van dijk", "van dijk", "NAME") in pairing for pairing in shape
    )
    # No pairing carries a NAME edge that's a strict-subset on the
    # same parts as the compound — those are pruned at step 2.
    for pairing in shape:
        assert ("van", "van", "NAME") not in pairing
        assert ("dijk", "dijk", "NAME") not in pairing
    # SYMBOL:van is a different category, so subsumption does not
    # apply — it survives and surfaces in a pairing alongside the
    # compound coverage it excludes.
    assert any(
        ("van", "van", "SYMBOL") in pairing for pairing in shape
    )


# --- ambiguity on the result side ---


def test_ambiguous_result_side():  # corpus-dependent
    # N=1 on query, M=2 on result. Bind one edge; one result-side
    # part remains unaligned. Greedy span-index binding picks the
    # first rspan — the "john" NAME span, not "johnny".
    q = _only(analyze_names(NameTypeTag.PER, ["John"]))
    r = _only(analyze_names(NameTypeTag.PER, ["John Johnny"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [("john", "john", "NAME")],
    ]


# --- org cases ---

# Note: the ORG/ENT pipeline runs `replace_org_types_compare` on the
# form BEFORE Name construction, so phrases like "Limited Liability
# Company" get rewritten to "llc" and the resulting `Name.parts`
# reflect the canonical form. Assertions below work against the
# post-rewrite shape.


def test_org_class_abbreviation():
    # "Ltd" and "Limited" both canonicalise to the same ORG_CLASS
    # form — after replace_org_types_compare, both names reduce to
    # the same token sequence and pair trivially on that token.
    q = _only(analyze_names(NameTypeTag.ORG, ["Acme Ltd"]))
    r = _only(analyze_names(NameTypeTag.ORG, ["Acme Limited"]))
    shape = pair_shape(pair_symbols(q, r))
    assert any(
        any(cat == "ORGCLS" for _, _, cat in pairing) for pairing in shape
    )


def test_org_class_position_independent():  # corpus-dependent
    # OOO is the Russian LLC-equivalent — if it canonicalises to the
    # same symbol as LLC in the corpus, the edge fires regardless of
    # whether the token appears as prefix or suffix.
    q = _only(analyze_names(NameTypeTag.ORG, ["OOO Garant"]))
    r = _only(analyze_names(NameTypeTag.ORG, ["Garant LLC"]))
    shape = pair_shape(pair_symbols(q, r))
    assert any(
        any(cat == "ORGCLS" for _, _, cat in pairing) for pairing in shape
    )


def test_company_pairs_ignoring_extra_qualifiers():  # corpus-dependent
    # "Company" is a generic qualifier that carries a symbol of its
    # own (SYMBOL:COMPANY or ORG_CLASS:CO, corpus-dependent). Both
    # sides of this pair tokenise with a `company`-class symbol,
    # so that token pairs. The extra `limited liability` qualifiers
    # on the result side have no query-side counterpart and stay
    # out of the pairing edges.
    q = _only(analyze_names(NameTypeTag.ORG, ["Stripe Company"]))
    r = _only(
        analyze_names(NameTypeTag.ORG, ["Stripe Limited Liability Company"])
    )
    shape = pair_shape(pair_symbols(q, r))
    for pairing in shape:
        r_parts_in_edges = set()
        for _, r_text, _ in pairing:
            r_parts_in_edges.update(r_text.split())
        assert "limited" not in r_parts_in_edges
        assert "liability" not in r_parts_in_edges


# --- cross-script ---


def test_cross_script_names():  # corpus-dependent
    # Latin "Vladimir Putin" and Cyrillic "Владимир Путин" share
    # NAME symbols via the Wikidata alias corpus. "Vladimirovich"
    # has no Cyrillic counterpart here and stays out of the edges.
    q = _only(analyze_names(NameTypeTag.PER, ["Vladimir Vladimirovich Putin"]))
    r = _only(analyze_names(NameTypeTag.PER, ["Владимир Путин"]))
    assert pair_shape(pair_symbols(q, r)) == [
        [
            ("putin", "путин", "NAME"),
            ("vladimir", "владимир", "NAME"),
        ],
    ]


# --- structural contracts ---


def test_empty_pairing_always_first():
    # The first pairing is always empty, so downstream callers have
    # a guaranteed fallback when no symbol coverage wins.
    q = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    r = _only(analyze_names(NameTypeTag.PER, ["John Smith"]))
    shape = pair_shape(pair_symbols(q, r))
    assert shape[0] == []


def test_too_many_parts_refuses_pairing():
    # Names with more than 64 parts blow past the u64 bitmask fast
    # path. Rather than fall back to Vec<u64> for inputs that are
    # almost always data errors (conglomerated legal-name blobs),
    # the algorithm short-circuits and returns the empty-only
    # fallback so downstream scoring runs on the full remainder.
    long_name = " ".join(f"zz{i:02d}" for i in range(70))
    q = _only(analyze_names(NameTypeTag.PER, [long_name]))
    r = _only(analyze_names(NameTypeTag.PER, [long_name]))
    assert len(q.parts) == 70
    assert pair_shape(pair_symbols(q, r)) == [[]]
