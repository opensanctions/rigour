from rigour.mime.filename import FileName


def test_none_filename():
    fn = FileName(None)
    assert fn.file_name is None
    assert fn.extension is None
    assert not fn.has_extension
    assert fn.safe() == "data"

def test_normal_filename():
    fn = FileName("testing .doc")
    assert fn.file_name == "testing .doc"
    assert fn.extension == "doc"
    assert fn.has_extension is True
    assert fn.safe() == "testing.doc"
    assert fn.safe("xls") == "testing.xls"
    assert str(fn) == 'testing .doc'
    assert 'testing.doc' in repr(fn) 

def test_no_ext_filename():
    fn = FileName("testing xxx")
    assert fn.extension is None
    assert fn.has_extension is False
    assert fn.safe() == "testing_xxx"
    assert fn.safe("doc") == "testing_xxx.doc"
    assert str(fn) == 'testing xxx'
