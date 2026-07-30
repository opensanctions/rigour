from normality import squash_spaces

from rigour.text.cleaning import remove_bracketed_text, remove_emoji


def test_remove_emoji():
    assert remove_emoji("abc") == "abc"
    assert remove_emoji("ab⚔️🚩cd") == "abcd"
    assert remove_emoji("\U0001f600\U0001f601") == ""
    assert remove_emoji("ЙГЗЖ") == "ЙГЗЖ"

    assert remove_emoji("卢拉玛·克辛瓜纳") == "卢拉玛·克辛瓜纳"


def test_remove_bracketed_text():
    assert remove_bracketed_text("abc") == "abc"
    assert (
        squash_spaces(remove_bracketed_text("Sean Connery (Actor)")) == "Sean Connery"
    )
    assert (
        remove_bracketed_text("Deutsche Bank Shanghai Ltd")
        == "Deutsche Bank Shanghai Ltd"
    )
    assert (
        squash_spaces(remove_bracketed_text("Deutsche Bank (Shanghai) Ltd"))
        == "Deutsche Bank Ltd"
    )
