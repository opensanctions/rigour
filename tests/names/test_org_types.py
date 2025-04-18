from rigour.names.org_types import replace_org_types_display as replace_display


def test_display_form():
    assert replace_display("Siemens Aktiengesellschaft") == "Siemens AG"
    assert replace_display("Siemens AG") == "Siemens AG"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long) == "Siemens GmbH"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long.upper()) == "Siemens GmbH".upper()
