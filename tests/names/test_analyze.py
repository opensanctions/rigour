"""Tests for rigour.names.analyze.analyze_names.

House style mirrors tests/names/test_tagging.py — one concept per
test, direct assertions on the returned `Name` objects' `.parts`,
`.spans`, `.symbols`, `.tag`, `.form`.
"""

from rigour.names import (
    Name,
    NamePartTag,
    NameTypeTag,
    Symbol,
    analyze_names,
)


def _only(names: set[Name]) -> Name:
    """Extract the single Name from a size-1 result set."""
    assert len(names) == 1, f"expected 1 Name, got {len(names)}: {names}"
    return next(iter(names))


def _part_tags(name: Name) -> dict[str, NamePartTag]:
    """Map `part.form` → `part.tag` for convenient assertion."""
    return {part.form: part.tag for part in name.parts}


# --- person names ---


def test_person_simple():
    result = analyze_names(NameTypeTag.PER, ["John Doe"])
    name = _only(result)
    assert name.tag == NameTypeTag.PER
    assert name.form == "john doe"
    assert [part.form for part in name.parts] == ["john", "doe"]


def test_person_with_part_tags():
    result = analyze_names(
        NameTypeTag.PER,
        ["John Doe"],
        {NamePartTag.GIVEN: ["John"], NamePartTag.FAMILY: ["Doe"]},
    )
    name = _only(result)
    tags = _part_tags(name)
    assert tags["john"] == NamePartTag.GIVEN
    assert tags["doe"] == NamePartTag.FAMILY


def test_person_three_tags_slavic():
    result = analyze_names(
        NameTypeTag.PER,
        ["Vladimir Vladimirovitch Putin"],
        {
            NamePartTag.GIVEN: ["Vladimir"],
            NamePartTag.MIDDLE: ["Vladimirovitch"],
            NamePartTag.FAMILY: ["Putin"],
        },
    )
    name = _only(result)
    tags = _part_tags(name)
    assert tags["vladimir"] == NamePartTag.GIVEN
    assert tags["vladimirovitch"] == NamePartTag.MIDDLE
    assert tags["putin"] == NamePartTag.FAMILY


def test_person_multi_token_given():
    # "Jean Claude" as a single GIVEN value should tag BOTH "jean" and
    # "claude" parts — Name.tag_text tokenises the value and walks the
    # name parts matching the sequence.
    result = analyze_names(
        NameTypeTag.PER,
        ["Jean Claude Juncker"],
        {
            NamePartTag.GIVEN: ["Jean Claude"],
            NamePartTag.FAMILY: ["Juncker"],
        },
    )
    name = _only(result)
    tags = _part_tags(name)
    assert tags["jean"] == NamePartTag.GIVEN
    assert tags["claude"] == NamePartTag.GIVEN
    assert tags["juncker"] == NamePartTag.FAMILY


# --- org / ENT names ---


def test_company_simple():
    # "Aktiengesellschaft" is the German spelt-out form of "AG" — the
    # org-types table rewrites it to "ag" at compare-form time.
    result = analyze_names(NameTypeTag.ORG, ["Siemens Aktiengesellschaft"])
    name = _only(result)
    assert name.form == "siemens ag"
    assert any(
        sym.category == Symbol.Category.ORG_CLASS for sym in name.symbols
    )


def test_entity_upgrade_to_org():
    # "Limited Liability Partnership" normalises to "llp" — single
    # ORG_CLASS span whose len(span) (character count) is 3 > 2.
    # _infer_part_tags promotes ENT → ORG on that threshold.
    result = analyze_names(
        NameTypeTag.ENT, ["Acme Limited Liability Partnership"]
    )
    name = _only(result)
    assert name.tag == NameTypeTag.ORG


def test_entity_no_upgrade():
    # ENT name without any ORG_CLASS span stays ENT.
    result = analyze_names(NameTypeTag.ENT, ["Apollo Missions Archive"])
    name = _only(result)
    assert name.tag == NameTypeTag.ENT


def test_org_prefix_stripped():
    # "The" is a configured org-prefix; remove_org_prefixes drops it.
    result = analyze_names(
        NameTypeTag.ORG, ["The Siemens Aktiengesellschaft"]
    )
    name = _only(result)
    assert not name.form.startswith("the ")
    assert "siemens" in name.form
    assert "ag" in name.form


# --- prefixes ---


def test_person_prefix_stripped():
    result = analyze_names(NameTypeTag.PER, ["Mr. John Smith"])
    name = _only(result)
    assert "mr" not in name.form.split()
    assert "john" in name.form.split()
    assert "smith" in name.form.split()


# --- infer_initials ---


def test_infer_initials_query_side():
    # Query-side "J Smith": single-char part gets INITIAL symbol.
    result = analyze_names(
        NameTypeTag.PER, ["J Smith"], infer_initials=True
    )
    name = _only(result)
    initials = {
        sym for sym in name.symbols if sym.category == Symbol.Category.INITIAL
    }
    assert Symbol(Symbol.Category.INITIAL, "j") in initials


def test_infer_initials_off():
    # Without the flag and without a GIVEN/MIDDLE tag on "J",
    # no INITIAL symbol fires.
    result = analyze_names(
        NameTypeTag.PER, ["J Smith"], infer_initials=False
    )
    name = _only(result)
    initials = {
        sym for sym in name.symbols if sym.category == Symbol.Category.INITIAL
    }
    assert Symbol(Symbol.Category.INITIAL, "j") not in initials


# --- consolidate ---


def test_consolidate_drops_substring():
    # Two input pairs, both should reduce to the longer name only
    # under the default `consolidate=True`.
    # Pair 1: adjacent-shape substring ("John Smith" ⊂ "John R Smith").
    short_long_adjacent = ["John Smith", "John R Smith"]
    pair1 = analyze_names(NameTypeTag.PER, short_long_adjacent)
    assert len(pair1) == 1
    assert _only(pair1).form == "john r smith"

    # Pair 2: non-adjacent substring with a Slavic patronymic — "Vladimir Putin"
    # tokens appear in "Vladimir Vladimirovitch Putin" but with a middle
    # part between them. Name.contains() for PER is adjacency-insensitive.
    short_long_slavic = [
        "Vladimir Putin",
        "Vladimir Vladimirovitch Putin",
    ]
    pair2 = analyze_names(NameTypeTag.PER, short_long_slavic)
    assert len(pair2) == 1
    assert _only(pair2).form == "vladimir vladimirovitch putin"

    # Opt-out: with consolidate=False both names survive — this is the
    # indexer-side mode that preserves partial-name recall.
    pair1_raw = analyze_names(
        NameTypeTag.PER, short_long_adjacent, consolidate=False
    )
    assert len(pair1_raw) == 2
    pair2_raw = analyze_names(
        NameTypeTag.PER, short_long_slavic, consolidate=False
    )
    assert len(pair2_raw) == 2


# --- numerics ---


def test_numerics_on_adds_symbol():
    # A large arbitrary number the AC ordinal list doesn't cover should
    # get a NUMERIC symbol when numerics=True.
    result = analyze_names(
        NameTypeTag.ORG, ["123456789 Battalion"], numerics=True
    )
    name = _only(result)
    numerics = [
        sym for sym in name.symbols if sym.category == Symbol.Category.NUMERIC
    ]
    assert Symbol(Symbol.Category.NUMERIC, 123456789) in numerics


def test_numerics_off_tags_but_no_symbol():
    result = analyze_names(
        NameTypeTag.ORG, ["123456789 Battalion"], numerics=False
    )
    name = _only(result)
    # Part still tagged NUM (cheap structural info).
    assert any(
        part.form == "123456789" and part.tag == NamePartTag.NUM
        for part in name.parts
    )
    # But no NUMERIC symbol emitted.
    numerics = [
        sym for sym in name.symbols if sym.category == Symbol.Category.NUMERIC
    ]
    assert Symbol(Symbol.Category.NUMERIC, 123456789) not in numerics


# --- dedup & edge cases ---


def test_dedup_by_form():
    # All three casefold to "ibm" — one Name in the result.
    result = analyze_names(NameTypeTag.ORG, ["IBM", "ibm", "Ibm"])
    assert len(result) == 1
    assert _only(result).form == "ibm"


def test_empty_names():
    assert analyze_names(NameTypeTag.PER, []) == set()
    assert analyze_names(NameTypeTag.ORG, []) == set()


def test_obj_type_tag_no_tagging():
    result = analyze_names(NameTypeTag.OBJ, ["Hubble Space Telescope"])
    name = _only(result)
    assert name.tag == NameTypeTag.OBJ
    assert name.symbols == set()


def test_unk_type_tag_no_tagging():
    result = analyze_names(NameTypeTag.UNK, ["some mystery string"])
    name = _only(result)
    assert name.tag == NameTypeTag.UNK
    assert name.symbols == set()
