from normality.transliteration import latinize_text
from rigour.reset import reset_caches


def test_reset_caches():
    latinize_text.cache_clear()
    assert latinize_text.cache_info().currsize == 0
    latinize_text("foo")
    assert latinize_text.cache_info().currsize == 1
    reset_caches()
    assert latinize_text.cache_info().currsize == 0
