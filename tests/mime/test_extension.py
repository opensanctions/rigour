from rigour.mime.filename import normalize_extension
from rigour.mime.filename import mimetype_extension as mime_ext


def test_normalize():
    assert normalize_extension(".doc") == "doc"
    assert normalize_extension(None) is None
    assert normalize_extension("") is None
    assert normalize_extension("bla.doc") == "doc"
    assert normalize_extension("bla.DOC") == "doc"
    assert normalize_extension("bla.DO C") == "doc"
    assert normalize_extension("bla.  DOC  ") == "doc"

    assert normalize_extension("TXT") == "txt"
    assert normalize_extension(".TXT") == "txt"
    assert normalize_extension("foo.txt") == "txt"
    assert normalize_extension("foo..TXT") == "txt"
    assert normalize_extension(".HTM,L") == "html"

def test_mimetype_extension():
    assert mime_ext(None) is None
    assert mime_ext("") is None
    assert mime_ext("bla") is None
    assert mime_ext("application/pdf") == "pdf"
