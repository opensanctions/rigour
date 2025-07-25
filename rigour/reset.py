import gc
from normality.transliteration import latinize_text

from rigour.text.distance import levenshtein, dam_levenshtein, jaro_winkler
from rigour.text.phonetics import soundex, metaphone
from rigour.text.scripts import should_latinize_cp
from rigour.names import normalize_name
from rigour.addresses.format import _load_formats, _load_template
from rigour.names.org_types import _compare_replacer, _display_replacer
from rigour.names.tagging import _get_org_tagger, _get_person_tagger


def reset_caches() -> None:
    """Reset LRU caches in the rigour module. This is meant to be used
    in long-lived processes to prevent memory expansion."""
    latinize_text.cache_clear()
    levenshtein.cache_clear()
    normalize_name.cache_clear()
    dam_levenshtein.cache_clear()
    jaro_winkler.cache_clear()
    soundex.cache_clear()
    metaphone.cache_clear()
    should_latinize_cp.cache_clear()
    _load_formats.cache_clear()
    _load_template.cache_clear()
    _compare_replacer.cache_clear()
    _display_replacer.cache_clear()
    _get_org_tagger.cache_clear()
    _get_person_tagger.cache_clear()
    gc.collect()
