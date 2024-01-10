from rigour.urls.compare import compare_urls

def test_compare_url():
    assert compare_urls("https://www.axample.com", "https://www.example.com") == 0.0
    assert compare_urls("", "") == 0.0
    assert compare_urls("https://www.example.com", "https://www.example.com") == 1.0
    assert compare_urls("http://www.example.com", "https://www.example.com/") == 1.0
    assert compare_urls("http://example.com", "https://www.example.com/") == 1.0
    assert compare_urls("example.com", "https://www.example.com/") == 1.0
    assert compare_urls("https://www.example.com", "//www.example.com/") == 1.0
    