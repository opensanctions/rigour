from typing import Optional

from rigour.names import Name, Symbol, NamePartTag, NameTypeTag
from rigour.names.part import NamePart
from rigour.names.tagging import tag_person_name, tag_org_name
from rigour.names.tokenize import prenormalize_name, tokenize_name

# For testing purposes, we only load these names by hacking the normalizer.
LOAD_COMPOUND = [
    "jae",
    "再",
    "ho",
    "하오",
    "jae-ho",
    "재호",
    "jeong",
    "郑",
    "jeong-jae",
    "정재",
]
LOAD_ONLY = [
    "john",
    "джон",
    "doe",
    "Dr",
    "Doktor",
    "jean",
    "жан",
    "claude",
    "клод",
    "jean-claude",
    "жан-клод",
] + LOAD_COMPOUND


def _per_normalizer(name: Optional[str]) -> Optional[str]:
    if name not in LOAD_ONLY:
        return None
    pre = prenormalize_name(name)
    return " ".join(tokenize_name(pre)) if pre else ""


def _org_normalizer(name: Optional[str]) -> Optional[str]:
    pre = prenormalize_name(name)
    return " ".join(tokenize_name(pre)) if pre else ""


def test_tag_person_name():
    """Test tagging a person name."""
    name = Name("John Doe")
    tagged_name = tag_person_name(name, _per_normalizer)

    # this might change a lot?
    john = Symbol(Symbol.Category.NAME, 4925477)

    jsym = Symbol(Symbol.Category.INITIAL, "j")
    assert tagged_name is not None
    assert tagged_name.comparable == "john doe"
    assert len(tagged_name.symbols) > 0
    assert john in tagged_name.symbols
    assert all(isinstance(symbol, Symbol) for symbol in tagged_name.symbols)
    assert jsym not in tagged_name.symbols

    name.tag_text("john", NamePartTag.GIVEN)
    name.tag_text("doe", NamePartTag.FAMILY)
    tagged_name = tag_person_name(name, _per_normalizer)
    assert jsym in tagged_name.symbols
    name = Name("J Doe", tag=NameTypeTag.PER)
    tagged_name = tag_person_name(name, _per_normalizer, any_initials=False)
    assert tagged_name is not None
    assert jsym not in tagged_name.symbols

    name = Name("J Doe", tag=NameTypeTag.PER)
    tagged_name = tag_person_name(name, _per_normalizer, any_initials=True)
    assert tagged_name is not None
    assert jsym in tagged_name.symbols

    # test an arabic name
    name = Name("أسامة")
    tagged_name = tag_person_name(name, _per_normalizer)
    assert tagged_name is not None
    assert tagged_name.comparable == "أسامة"
    assert len(tagged_name.symbols) == 0.0  # no loaded fixtures


def test_tag_person_name_overlapping():
    """
    Just documenting for now that jae-ho is not tagged by RE but jeong-jae is

    Same sort of thing for
    - বর য ন (3894860) in বর য ন ব রক
    - "da silva" in "adaias rodrigues da silva"
    - "james anthony" in "jonathan james anthony naden"
    """
    # It's important that these are distinct name instances
    #  - tag_person_name modifies the instance.
    name_ahocor = Name("jeong jae ho")
    name_ahocor = tag_person_name(name_ahocor, _per_normalizer)
    jae_ho = Symbol(Symbol.Category.NAME, 17151901)
    jeong = Symbol(Symbol.Category.NAME, 37489860)
    jeong_jae = Symbol(Symbol.Category.NAME, 69509157)
    ho = Symbol(Symbol.Category.NAME, 104377081)
    jae = Symbol(Symbol.Category.NAME, 16255943)
    all = {jae_ho, jeong, jeong_jae, ho, jae}
    assert all - name_ahocor.symbols == set()


def test_tag_person_multiple():
    """Test tagging a person name with multiple parts."""
    name = Name("Jean-Claude")
    tagged_name = tag_person_name(name, _per_normalizer)
    assert len(tagged_name.symbols) > 0
    stexts = [s.comparable for s in tagged_name.spans]
    assert "jean" in stexts
    assert "claude" in stexts
    assert "jean claude" in stexts

    name = Name("Jean-Claude, 2", tag=NameTypeTag.PER)
    tagged_name = tag_person_name(name, _per_normalizer)
    assert tagged_name.parts[-1].tag == NamePartTag.NUM


def test_tag_org_name():
    """Test tagging an organization name."""
    name = Name("Doe Industries, Inc.")
    tagged_name = tag_org_name(name, _org_normalizer)

    assert tagged_name is not None
    assert tagged_name.comparable == "doe industries inc"
    assert len(tagged_name.symbols) > 0
    indus = Symbol(Symbol.Category.SYMBOL, "INDUSTRY")
    assert indus in tagged_name.symbols
    assert len(tagged_name.spans) == 2
    # First span is "Doe Industries"
    assert tagged_name.spans[0].symbol.category == Symbol.Category.SYMBOL

    # Second span is "Inc." which maps to LLC
    llc_span = tagged_name.spans[1]
    assert llc_span.symbol.category == Symbol.Category.ORG_CLASS
    assert llc_span.symbol.id == "LLC"
    for part in llc_span.parts:
        assert part.tag == NamePartTag.LEGAL


def test_tag_org_name_location():
    """Test tagging an organization name with a location."""
    name = Name("Doe Industries (New York) Inc.")
    tagged_name = tag_org_name(name, _org_normalizer)

    assert tagged_name is not None
    assert len(tagged_name.symbols) > 0
    loc = Symbol(Symbol.Category.LOCATION, "us-ny")
    assert loc in tagged_name.symbols


def test_tag_org_name_sorting():
    # Legal tagged name parts go last in the sort order.
    name = Name("OOO ORION", tag=NameTypeTag.ORG)
    tagged_name = tag_org_name(name, _org_normalizer)
    sorted = NamePart.tag_sort(tagged_name.parts)
    assert sorted[0].form == "orion"


def test_tag_org_name_type_cast():
    name = Name("Benevolent Foundation", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer)
    assert tagged_name is not None
    assert tagged_name.tag == NameTypeTag.ENT

    name = Name("Benevolent, LLC", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer)
    assert tagged_name is not None
    assert tagged_name.tag == NameTypeTag.ORG

    name = Name("The Bow and Arrow", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer)
    assert tagged_name is not None
    assert tagged_name.parts[0].tag == NamePartTag.STOP
    assert tagged_name.parts[1].tag == NamePartTag.UNSET
    assert tagged_name.parts[2].tag == NamePartTag.STOP


def test_tag_org_name_ordinals():
    vars = ["5. Batallion", "5 Batallion", "Fifth Batallion"]
    for var in vars:
        name = Name(var, tag=NameTypeTag.ENT)
        tagged_name = tag_org_name(name, _org_normalizer)
        # assert tagged_name.parts[0].tag == NamePartTag.NUM
        assert len(tagged_name.symbols) > 0
        assert any(
            symbol.category == Symbol.Category.NUMERIC and symbol.id == 5
            for symbol in tagged_name.symbols
        )


def test_tag_org_name_large_num():
    name = Name("123456789 Batallion", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer)
    assert tagged_name.parts[0].tag == NamePartTag.NUM
    assert len(tagged_name.symbols) > 0
    assert any(
        symbol.category == Symbol.Category.NUMERIC and symbol.id == 123456789
        for symbol in tagged_name.symbols
    )
    name = Name("Rungra-888", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer)
    assert tagged_name.parts[1].tag == NamePartTag.NUM
    assert len(tagged_name.symbols) > 0
    assert any(
        symbol.category == Symbol.Category.NUMERIC and symbol.id == 888
        for symbol in tagged_name.symbols
    )


def test_tag_org_cyrillic_prefix():
    # Russian-style: org type precedes the name; ООО generic maps to "LLC"
    name = Name("ООО Газпром", tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    llc = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    assert llc in tagged.symbols
    legal_parts = [p for p in tagged.parts if p.tag == NamePartTag.LEGAL]
    # Only the ООО token should be legal-tagged, not Газпром
    assert len(legal_parts) == 1
    assert legal_parts[0].form == "ооо"


def test_tag_org_cjk():
    # Chinese company name with no spaces — must not crash
    name = Name("招商银行有限公司", tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    # 有限公司 is an alias (not a compare/display form), so the tagger never indexes it.
    # Current behavior: no ORG_CLASS detected for CJK-script input.
    ltd = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    assert ltd not in tagged.symbols


def test_tag_org_arabic_suffix():
    # Arabic company name — must not crash
    # المحدودة is an alias (not compare/display), so not in tagger mapping
    name = Name("شركة أرامكو السعودية المحدودة", tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    # Current behavior: no ORG_CLASS detected (alias-only form)
    ltd_syms = [s for s in tagged.symbols if s.category == Symbol.Category.ORG_CLASS]
    assert len(ltd_syms) == 0


def test_tag_org_no_false_positive():
    # Short org types (SA, AS, AG) must not produce ORG_CLASS spans inside longer words
    name = Name("Samsung Electronics", tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    org_class_spans = [s for s in tagged.spans if s.symbol.category == Symbol.Category.ORG_CLASS]
    assert len(org_class_spans) == 0


def test_tag_org_cyrillic_quoted_with_number():
    # Russian convention: ООО followed by quoted name containing a year/number
    # Quotes are stripped by the tokenizer, so parts become: ооо, аяс, 2000
    name = Name('ООО "АЯС 2000"', tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    llc = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    assert llc in tagged.symbols
    assert any(
        s.category == Symbol.Category.NUMERIC and s.id == 2000
        for s in tagged.symbols
    )


def test_tag_org_spzoo():
    # "Sp. z o.o." — Polish limited company. The tagger uses _org_normalizer which
    # strips dots via tokenize_name: "sp. z o.o." → tokens ["sp", "z", "oo"].
    # The tagger indexes the display form "Sp. z o.o." under key "sp z oo",
    # so it matches as a 3-token span in the name.
    name = Name("Faberlic Europe Sp. z o.o.", tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    llc = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    assert llc in tagged.symbols
    legal_parts = [p for p in tagged.parts if p.tag == NamePartTag.LEGAL]
    legal_forms = {p.form for p in legal_parts}
    # tokenize_name strips dots: "sp. z o.o." → sp, z, oo — all three are legal
    assert legal_forms == {"sp", "z", "oo"}


def test_tag_org_double_type():
    # Both AG (JSC) and GmbH (LLC) present in the same name —
    # both should be detected as ORG_CLASS symbols.
    name = Name("Siemens AG GmbH", tag=NameTypeTag.ORG)
    tagged = tag_org_name(name, _org_normalizer)
    assert tagged is not None
    jsc = Symbol(Symbol.Category.ORG_CLASS, "JSC")
    llc = Symbol(Symbol.Category.ORG_CLASS, "LLC")
    assert jsc in tagged.symbols
    assert llc in tagged.symbols
    legal_parts = [p for p in tagged.parts if p.tag == NamePartTag.LEGAL]
    assert len(legal_parts) == 2
