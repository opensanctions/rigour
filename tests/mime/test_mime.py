
from rigour.mime import parse_mimetype, normalize_mimetype, DEFAULT
from rigour.mime import useful_mimetype


def test_normalize():
    assert normalize_mimetype("TEXT/ PLAIN") == "text/plain"
    assert normalize_mimetype("TEXT/") == DEFAULT
    assert normalize_mimetype("1") == DEFAULT
    assert normalize_mimetype("1", default="") == ""
    assert normalize_mimetype(None) == DEFAULT

    PST = "application/VND.ms-outlook"
    assert normalize_mimetype(PST), PST.lower()


def test_useful():
    assert not useful_mimetype(None)
    assert not useful_mimetype(DEFAULT)
    assert useful_mimetype("image/png")


def test_label():
    parsed = parse_mimetype("application/x-pudo-banana")
    assert parsed.label == "pudo banana"


def test_parse():
    bad = parse_mimetype(None, default="")
    assert bad.label is None
    parsed = parse_mimetype("text/plain")
    assert parsed.charset is None
    assert parsed.label == "Plain text"
    assert parsed.family == "text"
    assert parsed.subtype == "plain"
    assert parsed.normalized == "text/plain"
    assert "%s" % parsed == "text/plain"
    assert "%r" % parsed == "text/plain"
    parsed = parse_mimetype("text/plain; charset=cp1251")
    assert parsed.charset == "cp1251"
    parsed = parse_mimetype("text/plain; charset=banana")
    assert parsed.charset == "utf-8"

    assert parsed == parse_mimetype("text/plain")
    assert hash(parse_mimetype("text/plain")) == hash(parsed)


def test_parse_rewrite():
    parsed = parse_mimetype("plain/text")
    assert parsed.normalized == "text/plain"
