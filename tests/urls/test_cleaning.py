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
    

def test_clean_url_junk_host():
    # Free text pasted into a website column: urlparse reads the prose as the
    # authority, so without a host check these come back as bogus URLs.
    assert clean_url("Social media: http://vk.com/sobolipress") is None
    assert clean_url("Official web site: http://soboli.net") is None
    assert clean_url("Website: www.example.com") is None
    assert clean_url("see the report on page 3.4 for details") is None
    assert clean_url("ул. Ленина, д. 5") is None
    assert clean_url("foo bar.baz qux") is None
    assert clean_url("http://exa mple.com/") is None
    assert clean_url("http://exa,mple.com/") is None
    assert clean_url("http://<none>/") is None
    # Values that only look like host names because they contain a dot.
    assert clean_url("3.4") is None
    assert clean_url("Nr. 12.5") is None
    assert clean_url("N.A.") is None
    assert clean_url("n/a") is None


def test_clean_url_idn():
    assert clean_url("русскоедвижение.рф") == "http://русскоедвижение.рф/"
    assert clean_url("http://www.русскоедвижение.рф/") == "http://www.русскоедвижение.рф/"
    assert clean_url("例え.テスト") == "http://例え.テスト/"
    assert clean_url("https://عربي.مصر") == "https://عربي.مصر/"
    assert clean_url("https://пример.рф/путь?q=да") == "https://пример.рф/путь?q=да"
    # The punycode encoding of the same domains must survive unchanged.
    assert clean_url("xn--80aa.xn--p1ai") == "http://xn--80aa.xn--p1ai/"
    assert clean_url("http://xn--e1afmkfd.xn--p1ai/path") == "http://xn--e1afmkfd.xn--p1ai/path"
    assert clean_url("XN--80AA.XN--P1AI") == "http://XN--80AA.XN--P1AI/"


def test_clean_url_authority():
    assert clean_url("https://user:pw@example.com:8443/x") == "https://user:pw@example.com:8443/x"
    assert clean_url("https://user@example.com/x") == "https://user@example.com/x"
    assert clean_url("http://192.168.0.1:8080/x") == "http://192.168.0.1:8080/x"
    assert clean_url("http://[2001:db8::1]/x") == "http://[2001:db8::1]/x"
    assert clean_url("http://[::1]:8000/") == "http://[::1]:8000/"
    assert clean_url("http://localhost:8000/") == "http://localhost:8000/"
    assert clean_url("http://example.com./") == "http://example.com./"
    assert clean_url("http://example.com:99999/") is None
    assert clean_url("http://example.com:port/") is None
    assert clean_url("http://:8080/") is None
    assert clean_url("http://user@/x") is None


def test_clean_url_labels():
    assert clean_url("example.co") == "http://example.co/"
    assert clean_url("http://ex-ample.co.uk/") == "http://ex-ample.co.uk/"
    assert clean_url("http://my_host.example.com/") == "http://my_host.example.com/"
    assert clean_url("http://foo..com/") is None
    assert clean_url("http://%s.com/" % ("a" * 64)) is None
    assert clean_url("http://./") is None
    assert clean_url("http://-/") is None
    assert clean_url("1.2.3.4.5.6") is None


def test_clean_url_scheme_without_host():
    # A supported scheme with no authority used to have a host invented from
    # its path, e.g. 'mailto:foo@bar.com' -> 'http://mailto:foo@bar.com/'.
    assert clean_url("mailto:foo@bar.com") is None
    assert clean_url("file:///tmp/foo.txt") is None
    assert clean_url("https:www.example.com") is None
    assert clean_url("s3://bucket/key.txt") == "s3://bucket/key.txt"


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
