from rigour.urls.cleaning import clean_url, clean_url_compare, build_url

def test_clean_url():
    assert clean_url("") is None
    assert clean_url("!!@@@@") is None
    assert clean_url("banana") is None
    assert clean_url("gopher://xxxx.com") is None
    assert clean_url("google.com") == "http://google.com/"
    assert clean_url("https://www.google.com") is not None
    assert clean_url("https://www.google.com") == "https://www.google.com/"
    assert clean_url("https://www.google.com/") == "https://www.google.com/"
    assert clean_url("https://www.google.com/ ") == "https://www.google.com/"
    assert clean_url("https://www.google.com/?q=foo") == "https://www.google.com/?q=foo"
    assert clean_url("https://www.google.com/?q=foo&bar=baz") == "https://www.google.com/?q=foo&bar=baz"
    

def test_clean_url_compare():
    assert clean_url_compare("") is None
    assert clean_url_compare("!!@@@@") is None
    assert clean_url_compare("banana") is None
    assert clean_url_compare("//google.com") == "http://google.com/"
    assert clean_url_compare("google.com") == "http://google.com/"
    assert clean_url_compare("https://www.google.com") is not None
    assert clean_url_compare("https://www.google.com") == "http://google.com/"
    assert clean_url_compare("https://www.google.com/") == "http://google.com/"
    assert clean_url_compare("https://www.google.com/ ") == "http://google.com/"
    assert clean_url_compare("https://www.google.com/?q=foo") == "http://google.com/?q=foo"
    assert clean_url_compare("https://www.google.com/?q=foo&bar=baz") == "http://google.com/?bar=baz&q=foo"


def test_build_url():
    assert build_url("http://pudo.org") == "http://pudo.org"
    assert build_url("http://pudo.org/blub") == "http://pudo.org/blub"
    assert build_url("http://pudo.org", {"q": "bla"}) == "http://pudo.org?q=bla"
    assert build_url("http://pudo.org", [("q", "bla")]) == "http://pudo.org?q=bla"
    assert (
        build_url("http://pudo.org?t=1", {"q": "bla"})
        == "http://pudo.org?t=1&q=bla"
    )
