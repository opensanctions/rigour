from rigour.names.org_types import replace_org_types_display as replace_display
from rigour.names.org_types import replace_org_types_compare as replace_compare
from rigour.names.org_types import extract_org_types, remove_org_types
from rigour.names.org_types import _normalize_compare
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
    assert replace_compare("siemens aktiengesellschaft") == "siemens ag"
    assert replace_compare("siemens ag") == "siemens ag"

    long = "siemens gesellschaft mit beschränkter Haftung"
    assert replace_compare(long) == "siemens gmbh"

    norm = _normalize_compare("FABERLIC EUROPE Sp. z o.o.")
    assert norm is not None
    assert extract_org_types(norm) == [("sp. z o.o.", "spzoo")]

    assert (
        replace_compare(norm, normalizer=_normalize_compare) == "faberlic europe spzoo"
    )


def test_extract_org_types():
    assert extract_org_types("siemens aktiengesellschaft") == [
        ("aktiengesellschaft", "ag")
    ]
    assert extract_org_types("siemens g.m.b.h") == [("g.m.b.h", "gmbh")]
    assert extract_org_types("siemens") == []


def test_remove_org_types():
    assert remove_org_types("siemens aktiengesellschaft").strip() == "siemens"
    assert remove_org_types("siemens g.m.b.h").strip() == "siemens"
    assert remove_org_types("siemens") == "siemens"
    assert remove_org_types("siemens  gmbh").strip() == "siemens"
    assert remove_org_types("siemens aktiengesellschaft gmbh").strip() == "siemens"
