from rigour.text.distance import levenshtein, dam_levenshtein
from rigour.text.distance import jaro_winkler
from rigour.text.distance import levenshtein_similarity


def test_levenshtein():
    assert levenshtein("foo", "foo") == 0
    assert levenshtein("foo", "bar") == 3
    assert levenshtein("bar", "bra") == 2
    assert levenshtein("foo", "foobar") == 3
    assert levenshtein("foo", "Foo") == 1


def test_levenshtein_dam():
    assert dam_levenshtein("foo", "foo") == 0
    assert dam_levenshtein("foo", "bar") == 3
    assert dam_levenshtein("bar", "bar") == 0
    assert dam_levenshtein("bar", "bra") == 1
    assert dam_levenshtein("foo", "foobar") == 3
    assert dam_levenshtein("foo", "Foo") == 1


def test_jaro_winkler():
    assert jaro_winkler("foo", "foo") == 1.0
    assert jaro_winkler("foo", "foox") > 0.9
    assert jaro_winkler("foo", "foox") < 1.0


def test_levenshtein_similarity():
    assert levenshtein_similarity("foo", "foo") == 1.0
    assert levenshtein_similarity("foo", "xxx") == 0.0
    assert levenshtein_similarity("", "") == 0.0
    assert levenshtein_similarity("banana", "banao") > 0.5
    assert levenshtein_similarity("banana", "banao") < 1.0
    assert levenshtein_similarity("banana", "banao", max_percent=0.2) == 0.0


def test_compare_levenshtein():
    assert levenshtein_similarity("John Smith", "John Smith") == 1.0
    johnny = levenshtein_similarity("John Smith", "Johnny Smith")
    assert johnny < 1.0
    assert johnny > 0.5
    johnathan = levenshtein_similarity("John Smith", "Johnathan Smith")
    assert johnathan < 1.0
    assert johnathan > 0.0
    assert levenshtein_similarity("John Smith", "Fredrick Smith") < 0.5
