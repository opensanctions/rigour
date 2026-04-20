from rigour.text.distance import levenshtein

from rigour.reset import reset_caches


def test_reset_caches():
    levenshtein.cache_clear()
    assert levenshtein.cache_info().currsize == 0
    levenshtein("foo", "bar")
    assert levenshtein.cache_info().currsize == 1
    reset_caches()
    assert levenshtein.cache_info().currsize == 0
