import pytest
from rigour.text.dictionary import Replacer, AhoCorReplacer
from rigour.names.org_types import replace_org_types_display as replace_display
from rigour.names.org_types import replace_org_types_compare as replace_compare
from rigour.names.org_types import extract_org_types, remove_org_types
from rigour.names.org_types import _normalize_compare

# from rigour.names.org_types import normalize_display


@pytest.mark.parametrize("clazz", [Replacer, AhoCorReplacer])
def test_display_form(clazz):
    assert replace_display("Siemens Aktiengesellschaft", replacer_class=clazz) == "Siemens AG"
    assert replace_display("Siemens AG", replacer_class=clazz) == "Siemens AG"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long, replacer_class=clazz) == "Siemens GmbH"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long.upper(), replacer_class=clazz) == "Siemens GmbH".upper()

    assert replace_display("Banana", replacer_class=clazz) == "Banana"
    assert replace_display("GmbH", replacer_class=clazz) == "GmbH"
    assert replace_display("GMBH", replacer_class=clazz) == "GMBH"


@pytest.mark.parametrize("clazz", [Replacer, AhoCorReplacer])
def test_compare_form(clazz):
    assert replace_compare("siemens aktiengesellschaft", replacer_class=clazz) == "siemens ag"
    assert replace_compare("siemens ag", replacer_class=clazz) == "siemens ag"
    assert replace_compare("siemens ag", generic=True, replacer_class=clazz) == "siemens jsc"

    long = "siemens gesellschaft mit beschränkter Haftung"
    assert replace_compare(long, replacer_class=clazz) == "siemens gmbh"

    norm = _normalize_compare("FABERLIC EUROPE Sp. z o.o.")
    assert norm is not None
    assert extract_org_types(norm, replacer_class=clazz) == [("sp. z o.o.", "spzoo")]
    assert replace_compare(norm, replacer_class=clazz) == "faberlic europe spzoo"


@pytest.mark.parametrize("clazz", [Replacer, AhoCorReplacer])
def test_extract_org_types(clazz):
    assert extract_org_types("siemens aktiengesellschaft", replacer_class=clazz) == [
        ("aktiengesellschaft", "ag")
    ]
    assert extract_org_types("siemens g.m.b.h", replacer_class=clazz) == [("g.m.b.h", "gmbh")]
    assert extract_org_types("siemens g.m.b.h", generic=True, replacer_class=clazz) == [("g.m.b.h", "llc")]
    assert extract_org_types("siemens", replacer_class=clazz) == []


@pytest.mark.parametrize("clazz", [Replacer, AhoCorReplacer])
def test_remove_org_types(clazz):
    assert remove_org_types("siemens aktiengesellschaft", replacer_class=clazz).strip() == "siemens"
    assert remove_org_types("siemens g.m.b.h", replacer_class=clazz).strip() == "siemens"
    assert remove_org_types("siemens", replacer_class=clazz) == "siemens"
    assert remove_org_types("siemens  gmbh", replacer_class=clazz).strip() == "siemens"
    assert remove_org_types("siemens aktiengesellschaft gmbh", replacer_class=clazz).strip() == "siemens"
