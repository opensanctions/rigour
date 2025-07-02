from typing import Optional

import pytest

from rigour.names import Name, Symbol, NamePartTag, NameTypeTag
from rigour.names.part import NamePart
from rigour.names.tagging import TaggerType, _get_person_tagger, tag_person_name, tag_org_name
from rigour.names.tokenize import prenormalize_name, tokenize_name

# For testing purposes, we only load these names by hacking the normalizer.
LOAD_COMPOUND = ["jae", "ho", "jae-ho", "jeong", "jeong-jae"]
LOAD_ONLY = ["john", "doe", "Dr", "Doktor", "jean", "claude", "jean-claude"] + LOAD_COMPOUND


def _per_normalizer(name: Optional[str]) -> Optional[str]:
    if name not in LOAD_ONLY:
        return None
    pre = prenormalize_name(name)
    return " ".join(tokenize_name(pre)) if pre else ""


def _org_normalizer(name: Optional[str]) -> Optional[str]:
    pre = prenormalize_name(name)
    return " ".join(tokenize_name(pre)) if pre else ""


@pytest.mark.parametrize("tagger_type", [TaggerType.RE, TaggerType.AHO_COR])
def test_tag_person_name(tagger_type):
    """Test tagging a person name."""
    name = Name("John Doe")
    tagged_name = tag_person_name(name, _per_normalizer, tagger_type=tagger_type)

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
    tagged_name = tag_person_name(name, _per_normalizer, tagger_type=tagger_type)
    assert jsym in tagged_name.symbols
    name = Name("J Doe", tag=NameTypeTag.PER)
    tagged_name = tag_person_name(
        name, _per_normalizer, any_initials=False, tagger_type=tagger_type
    )
    assert tagged_name is not None
    assert jsym not in tagged_name.symbols

    name = Name("J Doe", tag=NameTypeTag.PER)
    tagged_name = tag_person_name(
        name, _per_normalizer, any_initials=True, tagger_type=tagger_type
    )
    assert tagged_name is not None
    assert jsym in tagged_name.symbols


def test_tag_person_name_overlapping():
    """
    Just documenting for now that jae-ho is not tagged by RE but jeong-jae is

    Same sort of thing for
    - বর য ন (3894860) in বর য ন ব রক
    - "da silva" in "adaias rodrigues da silva"
    - "james anthony" in "jonathan james anthony naden"
    """
    tagged_re = tag_person_name(Name("jeong jae ho"), _per_normalizer, tagger_type=TaggerType.RE)
    tagged_aho_cor = tag_person_name(Name("jeong jae ho"), _per_normalizer, tagger_type=TaggerType.AHO_COR)
    jae_ho = Symbol(Symbol.Category.NAME, 17151901)
    jeong = Symbol(Symbol.Category.NAME, 37489860)
    jeong_jae = Symbol(Symbol.Category.NAME, 69509157)
    ho = Symbol(Symbol.Category.NAME, 104377081)
    jae = Symbol(Symbol.Category.NAME, 16255943)
    all = {jae_ho, jeong, jeong_jae, ho, jae}
    assert all - tagged_re.symbols == {jae_ho}
    assert all - tagged_aho_cor.symbols == set()


@pytest.mark.parametrize("tagger_type", [TaggerType.RE, TaggerType.AHO_COR])
def test_tag_person_multiple(tagger_type):
    """Test tagging a person name with multiple parts."""
    name = Name("Jean-Claude")
    tagged_name = tag_person_name(name, _per_normalizer)
    assert len(tagged_name.symbols) > 0
    stexts = [s.comparable for s in tagged_name.spans]
    assert "jean" in stexts
    assert "claude" in stexts
    assert "jean claude" in stexts

    name = Name("Jean-Claude, 2", tag=NameTypeTag.PER)
    tagged_name = tag_person_name(name, _per_normalizer, tagger_type)
    assert tagged_name.parts[-1].tag == NamePartTag.NUMERIC


@pytest.mark.parametrize("tagger_type", [TaggerType.RE, TaggerType.AHO_COR])
def test_tag_org_name(tagger_type):
    """Test tagging an organization name."""
    name = Name("Doe Industries, Inc.")
    tagged_name = tag_org_name(name, _org_normalizer, tagger_type)

    assert tagged_name is not None
    assert tagged_name.comparable == "doe industries inc"
    assert len(tagged_name.symbols) > 0
    indus = Symbol(Symbol.Category.SYMBOL, "INDUSTRY")
    assert indus in tagged_name.symbols
    for span in tagged_name.spans:
        if span.symbol.category == Symbol.Category.SYMBOL:
            continue
        assert span.symbol.category == Symbol.Category.ORG_CLASS
        assert span.symbol.id == "LLC"
        for part in span.parts:
            assert part.tag == NamePartTag.LEGAL


@pytest.mark.parametrize("tagger_type", [TaggerType.RE, TaggerType.AHO_COR])
def test_tag_org_name_sorting(tagger_type):
    # Legal tagged name parts go last in the sort order.
    name = Name("OOO ORION", tag=NameTypeTag.ORG)
    tagged_name = tag_org_name(name, _org_normalizer, tagger_type)
    sorted = NamePart.tag_sort(tagged_name.parts)
    assert sorted[0].form == "orion"


@pytest.mark.parametrize("tagger_type", [TaggerType.RE, TaggerType.AHO_COR])
def test_tag_org_name_type_cast(tagger_type):
    name = Name("Benevolent Foundation", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer, tagger_type)
    assert tagged_name is not None
    assert tagged_name.tag == NameTypeTag.ENT

    name = Name("Benevolent, LLC", tag=NameTypeTag.ENT)
    tagged_name = tag_org_name(name, _org_normalizer, tagger_type)
    assert tagged_name is not None
    assert tagged_name.tag == NameTypeTag.ORG


@pytest.mark.parametrize("tagger_type", [TaggerType.RE, TaggerType.AHO_COR])
def test_tag_org_name_ordinals(tagger_type):
    vars = ["5. Batallion", "5 Batallion", "Fifth Batallion"]
    for var in vars:
        name = Name(var, tag=NameTypeTag.ENT)
        tagged_name = tag_org_name(name, _org_normalizer, tagger_type)
        assert tagged_name.parts[0].tag == NamePartTag.NUMERIC
        assert len(tagged_name.symbols) > 0
        assert any(
            symbol.category == Symbol.Category.ORDINAL and symbol.id == 5
            for symbol in tagged_name.symbols
        )
