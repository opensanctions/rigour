from rigour.boolean import bool_text, text_bool


def test_bool_text():
    assert bool_text(None) is None
    assert bool_text(True) == "t"
    assert bool_text(False) == "f"


def test_text_bool():
    assert text_bool(None) is None
    assert text_bool("") is None
    assert text_bool("t") is True
    assert text_bool("T") is True
    assert text_bool("true") is True
    assert text_bool("True") is True
    assert text_bool("1") is True
    assert text_bool("y") is True
    assert text_bool("Y") is True
    assert text_bool("yes") is True
    assert text_bool("Yes") is True
    assert text_bool("f") is False
    assert text_bool("F") is False
    assert text_bool("false") is False
    assert text_bool("False") is False
    assert text_bool("0") is False
