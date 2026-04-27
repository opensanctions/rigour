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


# --- symbols master switch ---


def test_symbols_off_strips_all_symbols():
    # An ORG fixture that would normally emit ORG_CLASS ("ag") and
    # NUMERIC (for the large number) symbols: both are absent when
    # symbols=False.
    result = analyze_names(
        NameTypeTag.ORG, ["Siemens 123456789 Aktiengesellschaft"], symbols=False
    )
    name = _only(result)
    assert name.symbols == set()

    # A PER fixture with infer_initials=True would normally emit an
    # INITIAL symbol for "j": also absent when symbols=False
    # (infer_initials becomes a no-op).
    result_per = analyze_names(
        NameTypeTag.PER, ["J Smith"], infer_initials=True, symbols=False
    )
    name_per = _only(result_per)
    assert name_per.symbols == set()


def test_symbols_off_preserves_part_tags_and_num_tag():
    # NamePartTag labelling still fires on UNSET numeric parts,
    # and part_tags values are still applied via Name.tag_text.
    result = analyze_names(
        NameTypeTag.ORG,
        ["Acme 123456789 Holdings"],
        {NamePartTag.LEGAL: ["Holdings"]},
        symbols=False,
    )
    name = _only(result)
    assert name.symbols == set()
    tags = _part_tags(name)
    # UNSET → NUM promotion from the inference pass.
    assert tags["123456789"] == NamePartTag.NUM
    # part_tags application via Name.tag_text is independent of symbol emission.
    assert tags["holdings"] == NamePartTag.LEGAL


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


def test_obj_prefix_stripped_when_rewrite():
    result = analyze_names(NameTypeTag.OBJ, ["M/V Oceanic"])
    name = _only(result)
    assert name.original == "M/V Oceanic"
    assert "m/v" not in name.form
    assert name.form.endswith("oceanic")


def test_obj_prefix_kept_when_rewrite_false():
    result = analyze_names(NameTypeTag.OBJ, ["M/V Oceanic"], rewrite=False)
    name = _only(result)
    assert "m/v" in name.form


def test_unk_type_tag_no_tagging():
    result = analyze_names(NameTypeTag.UNK, ["some mystery string"])
    name = _only(result)
    assert name.tag == NameTypeTag.UNK
    assert name.symbols == set()


# --- rewrite=False: tagger-only mode (canonicalisation skipped) ---
#
# With `rewrite=False` the pipeline skips honorific/article prefix
# removal and org-type compare-form substitution. The tagger still
# fires on the raw tokens because its alias set covers both
# original and canonical forms. These tests exercise the tagger's
# behaviour on literal input.


def test_raw_person_name_corpus_match():
    # Wikidata QID match: the tagger's person-names corpus maps
    # "John" to its canonical NAME symbol. The exact QID may shift
    # if the corpus regenerates; the shape (some NAME symbol for
    # "John" in the symbols set) is what's stable.
    result = analyze_names(NameTypeTag.PER, ["John Doe"], rewrite=False)
    name = _only(result)
    assert name.comparable == "john doe"
    john = Symbol(Symbol.Category.NAME, "Q4925477")
    assert john in name.symbols


def test_raw_person_name_initial_from_given_tag():
    # Without a GIVEN/MIDDLE part tag, "John" is UNSET after
    # tokenisation and doesn't pick up an INITIAL symbol.
    jsym = Symbol(Symbol.Category.INITIAL, "j")
    result = analyze_names(NameTypeTag.PER, ["John Doe"], rewrite=False)
    name = _only(result)
    assert jsym not in name.symbols

    # Pre-tagging "John" as GIVEN triggers the INITIAL preamble to
    # emit INITIAL:j for the first char.
    result = analyze_names(
        NameTypeTag.PER,
        ["John Doe"],
        {NamePartTag.GIVEN: ["John"], NamePartTag.FAMILY: ["Doe"]},
        rewrite=False,
    )
    name = _only(result)
    assert jsym in name.symbols


def test_raw_person_initial_infer_flag():
    # Single-character part: only picks up INITIAL when
    # `infer_initials=True` (query-side behaviour).
    jsym = Symbol(Symbol.Category.INITIAL, "j")

    result_off = analyze_names(
        NameTypeTag.PER, ["J Doe"], infer_initials=False, rewrite=False
    )
    assert jsym not in _only(result_off).symbols

    result_on = analyze_names(
        NameTypeTag.PER, ["J Doe"], infer_initials=True, rewrite=False
    )
    assert jsym in _only(result_on).symbols


def test_raw_person_name_arabic_pass_through():
    # Arabic given name: corpus coverage varies, so we assert only
    # that the pipeline completes without error and preserves the
    # input form.
    result = analyze_names(NameTypeTag.PER, ["أسامة"], rewrite=False)
    name = _only(result)
    assert name.comparable == "أسامة"


def test_raw_person_name_korean_overlapping():
    # Korean compound names: the person-names corpus has entries
    # mapping multiple Wikidata QIDs to overlapping form sets.
    # With overlapping AC matching, every recognised phrase lands
    # as its own Span. Smoke-checks that five expected QIDs all
    # surface.
    result = analyze_names(NameTypeTag.PER, ["jeong jae ho"], rewrite=False)
    name = _only(result)
    jae_ho = Symbol(Symbol.Category.NAME, "Q17151901")
    jeong = Symbol(Symbol.Category.NAME, "Q37489860")
    jeong_jae = Symbol(Symbol.Category.NAME, "Q69509157")
    ho = Symbol(Symbol.Category.NAME, "Q104377081")
    jae = Symbol(Symbol.Category.NAME, "Q16255943")
    assert {jae_ho, jeong, jeong_jae, ho, jae} - name.symbols == set()


def test_raw_person_multi_token_spans():
    # "Jean-Claude" tokenises to ["jean", "claude"] and the tagger
    # matches "jean", "claude", and the compound "jean claude" —
    # each as an independent span.
    result = analyze_names(NameTypeTag.PER, ["Jean-Claude"], rewrite=False)
    name = _only(result)
    span_texts = {s.comparable for s in name.spans}
    assert "jean" in span_texts
    assert "claude" in span_texts
    assert "jean claude" in span_texts


def test_raw_person_numeric_part_tagging():
    # Trailing numeric part gets NamePartTag.NUM from the inference
    # pass, regardless of symbol emission.
    result = analyze_names(
        NameTypeTag.PER, ["Jean-Claude, 2"], rewrite=False
    )
    name = _only(result)
    assert name.parts[-1].tag == NamePartTag.NUM


def test_raw_org_industry_and_org_class():
    # "Doe Industries, Inc." — with rewrite off, `Inc.` stays
    # literal and the tagger emits ORG_CLASS:LLC on the "inc" token.
    # "Industries" fires SYMBOL:INDUSTRY as a generic-qualifier hit.
    result = analyze_names(
        NameTypeTag.ORG, ["Doe Industries, Inc."], rewrite=False
    )
    name = _only(result)
    assert name.comparable == "doe industries inc"
    indus = Symbol(Symbol.Category.SYMBOL, "INDUSTRY")
    assert indus in name.symbols
    assert len(name.spans) == 2
    # First span is the SYMBOL:INDUSTRY on "industries".
    assert name.spans[0].symbol.category == Symbol.Category.SYMBOL
    # Second span is the ORG_CLASS on "inc".
    llc_span = name.spans[1]
    assert llc_span.symbol.category == Symbol.Category.ORG_CLASS
    assert llc_span.symbol.id == "LLC"
    for part in llc_span.parts:
        assert part.tag == NamePartTag.LEGAL


def test_raw_org_name_location():
    # Location symbol on a territory name inside a company name.
    result = analyze_names(
        NameTypeTag.ORG, ["Doe Industries (New York) Inc."], rewrite=False
    )
    name = _only(result)
    assert Symbol(Symbol.Category.LOCATION, "us-ny") in name.symbols


def test_raw_org_tag_sort_legal_last():
    # After tagging, LEGAL-tagged parts sort last (display order).
    from rigour.names.part import NamePart

    result = analyze_names(NameTypeTag.ORG, ["OOO ORION"], rewrite=False)
    name = _only(result)
    assert NamePart.tag_sort(list(name.parts))[0].form == "orion"


def test_raw_ent_stays_ent_without_orgclass():
    # ENT without a long-enough ORG_CLASS span keeps its ENT tag.
    result = analyze_names(
        NameTypeTag.ENT, ["Benevolent Foundation"], rewrite=False
    )
    assert _only(result).tag == NameTypeTag.ENT


def test_raw_ent_upgrades_to_org_on_orgclass():
    # ORG_CLASS span longer than 2 chars promotes ENT → ORG.
    result = analyze_names(
        NameTypeTag.ENT, ["Benevolent, LLC"], rewrite=False
    )
    assert _only(result).tag == NameTypeTag.ORG


def test_raw_ent_stopword_tagging():
    # Stopwords like "the" / "and" get NamePartTag.STOP from the
    # inference pass; other UNSET parts remain UNSET.
    result = analyze_names(
        NameTypeTag.ENT, ["The Bow and Arrow"], rewrite=False
    )
    name = _only(result)
    tags = _part_tags(name)
    assert tags["the"] == NamePartTag.STOP
    assert tags["bow"] == NamePartTag.UNSET
    assert tags["and"] == NamePartTag.STOP


def test_raw_org_ordinals_to_numeric():
    # Ordinal markers ("5.", "5", "Fifth") all normalise to the same
    # NUMERIC:5 symbol via the tagger's ordinal corpus + the
    # trailing-period tokeniser behaviour.
    for variant in ["5. Batallion", "5 Batallion", "Fifth Batallion"]:
        result = analyze_names(NameTypeTag.ENT, [variant], rewrite=False)
        name = _only(result)
        assert any(
            sym.category == Symbol.Category.NUMERIC and sym.id == "5"
            for sym in name.symbols
        ), variant


def test_raw_org_large_numbers_get_numeric_symbol():
    # Large arbitrary numbers outside the ordinal corpus still get
    # a NUMERIC symbol via the inference pass.
    result = analyze_names(
        NameTypeTag.ENT, ["123456789 Batallion"], rewrite=False
    )
    name = _only(result)
    assert name.parts[0].tag == NamePartTag.NUM
    assert any(
        sym.category == Symbol.Category.NUMERIC and sym.id == "123456789"
        for sym in name.symbols
    )

    # Number after a hyphen — the tokeniser splits on punctuation so
    # "Rungra-888" becomes ["rungra", "888"].
    result = analyze_names(NameTypeTag.ENT, ["Rungra-888"], rewrite=False)
    name = _only(result)
    assert name.parts[1].tag == NamePartTag.NUM
    assert any(
        sym.category == Symbol.Category.NUMERIC and sym.id == "888"
        for sym in name.symbols
    )


def test_raw_org_cyrillic_prefix():
    # Russian convention: the org-type token ("ООО") appears before
    # the company name and maps to ORG_CLASS:LLC. Only the ООО
    # token should be LEGAL-tagged — not Газпром.
    result = analyze_names(NameTypeTag.ORG, ["ООО Газпром"], rewrite=False)
    name = _only(result)
    llc = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    assert llc in name.symbols
    legal_parts = [p for p in name.parts if p.tag == NamePartTag.LEGAL]
    assert len(legal_parts) == 1
    assert legal_parts[0].form == "ооо"


def test_raw_org_cjk_pass_through():
    # Chinese company name (no spaces) must not crash. 有限公司
    # is in the alias-only form — not in compare/display — so the
    # tagger's corpus doesn't index it and no ORG_CLASS fires.
    result = analyze_names(NameTypeTag.ORG, ["招商银行有限公司"], rewrite=False)
    name = _only(result)
    assert Symbol(Symbol.Category.ORG_CLASS, "LLC") not in name.symbols


def test_raw_org_arabic_pass_through():
    # Arabic company name must not crash. المحدودة is
    # alias-only — absent from the tagger's compare/display
    # mapping — so no ORG_CLASS symbol fires.
    result = analyze_names(
        NameTypeTag.ORG, ["شركة أرامكو السعودية المحدودة"], rewrite=False
    )
    name = _only(result)
    assert not any(
        sym.category == Symbol.Category.ORG_CLASS for sym in name.symbols
    )


def test_raw_org_no_false_positive_in_longer_word():
    # Short org-type tokens (SA, AS, AG) must not match inside
    # longer words. "Samsung" ends in "sa-ng" but shouldn't trigger
    # an ORG_CLASS:SA match.
    result = analyze_names(
        NameTypeTag.ORG, ["Samsung Electronics"], rewrite=False
    )
    name = _only(result)
    assert not any(
        s.symbol.category == Symbol.Category.ORG_CLASS for s in name.spans
    )


def test_raw_org_cyrillic_quoted_with_number():
    # Russian-style quoted company name with a year. Quotes are
    # stripped by the tokeniser; parts become [ооо, аяс, 2000].
    result = analyze_names(
        NameTypeTag.ORG, ['ООО "АЯС 2000"'], rewrite=False
    )
    name = _only(result)
    assert Symbol(Symbol.Category.ORG_CLASS, "LLC") in name.symbols
    assert any(
        s.category == Symbol.Category.NUMERIC and s.id == "2000"
        for s in name.symbols
    )


def test_raw_org_polish_sp_z_oo():
    # "Sp. z o.o." — Polish limited-company form. tokenize_name
    # strips periods, yielding ["sp", "z", "oo"]; the tagger has
    # this exact three-token phrase as an ORG_CLASS:LLC alias, so
    # all three tokens end up LEGAL-tagged.
    result = analyze_names(
        NameTypeTag.ORG, ["Faberlic Europe Sp. z o.o."], rewrite=False
    )
    name = _only(result)
    assert Symbol(Symbol.Category.ORG_CLASS, "LLC") in name.symbols
    legal_forms = {p.form for p in name.parts if p.tag == NamePartTag.LEGAL}
    assert legal_forms == {"sp", "z", "oo"}


def test_raw_org_double_legal_type():
    # Two different org-class markers in one name: both fire, both
    # parts are LEGAL.
    result = analyze_names(
        NameTypeTag.ORG, ["Siemens AG GmbH"], rewrite=False
    )
    name = _only(result)
    assert Symbol(Symbol.Category.ORG_CLASS, "JSC") in name.symbols
    assert Symbol(Symbol.Category.ORG_CLASS, "LLC") in name.symbols
    assert len([p for p in name.parts if p.tag == NamePartTag.LEGAL]) == 2
