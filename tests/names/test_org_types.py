from rigour.names.org_types import replace_org_types_display as replace_display
from rigour.names.org_types import replace_org_types_compare as replace_compare
from rigour.names.org_types import extract_org_types, remove_org_types
# from rigour.names.org_types import _normalize_compare
# from rigour.names.org_types import normalize_display


def test_display_form():
    assert replace_display("Siemens Aktiengesellschaft") == "Siemens AG"
    assert replace_display("Siemens AG") == "Siemens AG"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long) == "Siemens GmbH"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long.upper()) == "Siemens GmbH".upper()

    assert replace_display("Banana") == "Banana"
    assert replace_display("GmbH") == "GmbH"
    assert replace_display("GMBH") == "GMBH"


def test_compare_form():
    assert replace_compare("siemens aktiengesellschaft") == "siemens jsc"
    assert replace_compare("siemens ag") == "siemens jsc"

    long = "siemens gesellschaft mit beschränkter Haftung"
    assert replace_compare(long) == "siemens llc"


def test_extract_org_types():
    assert extract_org_types("siemens aktiengesellschaft") == [
        ("aktiengesellschaft", "jsc")
    ]
    assert extract_org_types("siemens g.m.b.h") == [("g.m.b.h", "llc")]
    assert extract_org_types("siemens") == []


def test_remove_org_types():
    assert remove_org_types("siemens aktiengesellschaft").strip() == "siemens"
    assert remove_org_types("siemens g.m.b.h").strip() == "siemens"
    assert remove_org_types("siemens") == "siemens"
    assert remove_org_types("siemens aktiengesellschaft gmbh").strip() == "siemens"
