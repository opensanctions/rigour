import gc
from normality.transliteration import latinize_text

from rigour.text.distance import levenshtein, dam_levenshtein, jaro_winkler
from rigour.text.phonetics import soundex, metaphone
from rigour.text.scripts import (
    char_tags,
    is_alpha,
    is_alphanum,
    is_modern_alphabet_char,
    is_latin_char,
)
from rigour.addresses.format import _load_formats, _load_template
from rigour.names.org_types import _compare_replacer, _display_replacer


def reset_caches() -> None:
    """Reset LRU caches in the rigour module. This is meant to be used
    in long-lived processes to prevent memory expansion."""
    latinize_text.cache_clear()
    levenshtein.cache_clear()
    dam_levenshtein.cache_clear()
    jaro_winkler.cache_clear()
    soundex.cache_clear()
    metaphone.cache_clear()
    is_modern_alphabet_char.cache_clear()
    is_latin_char.cache_clear()
    char_tags.cache_clear()
    is_alpha.cache_clear()
    is_alphanum.cache_clear()
    _load_formats.cache_clear()
    _load_template.cache_clear()
    _compare_replacer.cache_clear()
    _display_replacer.cache_clear()
    gc.collect()
