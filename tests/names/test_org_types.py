import pytest
from rigour.text.dictionary import REReplacer, AhoCorReplacer
from rigour.names.org_types import replace_org_types_display as replace_display
from rigour.names.org_types import replace_org_types_compare as replace_compare
from rigour.names.org_types import extract_org_types, remove_org_types
from rigour.names.org_types import _normalize_compare, ReplacerType

# from rigour.names.org_types import normalize_display


@pytest.mark.parametrize("tagger_type", [ReplacerType.RE, ReplacerType.AHO_COR])
def test_display_form(tagger_type):
    assert replace_display("Siemens Aktiengesellschaft", replacer_type=tagger_type) == "Siemens AG"
    assert replace_display("Siemens AG", replacer_type=tagger_type) == "Siemens AG"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long, replacer_type=tagger_type) == "Siemens GmbH"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long.upper(), replacer_type=tagger_type) == "Siemens GmbH".upper()

    assert replace_display("Banana", replacer_type=tagger_type) == "Banana"
    assert replace_display("GmbH", replacer_type=tagger_type) == "GmbH"
    assert replace_display("GMBH", replacer_type=tagger_type) == "GMBH"


@pytest.mark.parametrize("tagger_type", [ReplacerType.RE, ReplacerType.AHO_COR])
def test_compare_form(tagger_type):
    assert replace_compare("siemens aktiengesellschaft", replacer_type=tagger_type) == "siemens ag"
    assert replace_compare("siemens ag", replacer_type=tagger_type) == "siemens ag"
    assert replace_compare("siemens ag", generic=True, replacer_type=tagger_type) == "siemens jsc"

    long = "siemens gesellschaft mit beschränkter Haftung"
    assert replace_compare(long, replacer_type=tagger_type) == "siemens gmbh"

    norm = _normalize_compare("FABERLIC EUROPE Sp. z o.o.")
    assert norm is not None
    assert extract_org_types(norm, replacer_type=tagger_type) == [("sp. z o.o.", "spzoo")]
    assert replace_compare(norm, replacer_type=tagger_type) == "faberlic europe spzoo"


@pytest.mark.parametrize("tagger_type", [ReplacerType.RE, ReplacerType.AHO_COR])
def test_extract_org_types(tagger_type):
    assert extract_org_types("siemens aktiengesellschaft", replacer_type=tagger_type) == [
        ("aktiengesellschaft", "ag")
    ]
    assert extract_org_types("siemens g.m.b.h", replacer_type=tagger_type) == [("g.m.b.h", "gmbh")]
    assert extract_org_types("siemens g.m.b.h", generic=True, replacer_type=tagger_type) == [("g.m.b.h", "llc")]
    assert extract_org_types("siemens", replacer_type=tagger_type) == []


@pytest.mark.parametrize("tagger_type", [ReplacerType.RE, ReplacerType.AHO_COR])
def test_remove_org_types(tagger_type):
    assert remove_org_types("siemens aktiengesellschaft", replacer_type=tagger_type).strip() == "siemens"
    assert remove_org_types("siemens g.m.b.h", replacer_type=tagger_type).strip() == "siemens"
    assert remove_org_types("siemens", replacer_type=tagger_type) == "siemens"
    assert remove_org_types("siemens  gmbh", replacer_type=tagger_type).strip() == "siemens"
    assert remove_org_types("siemens aktiengesellschaft gmbh", replacer_type=tagger_type).strip() == "siemens"
