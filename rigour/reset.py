import gc
from normality.transliteration import latinize_text, _ascii_text

from rigour.text.distance import levenshtein, dam_levenshtein, jaro_winkler
from rigour.text.phonetics import soundex, metaphone
from rigour.territories.territory import get_index
from rigour.territories.lookup import lookup_territory
from rigour.territories.lookup import _get_identifier_map, _get_territory_names
from rigour.text.scripts import can_latinize_cp
from rigour.names import normalize_name
from rigour.addresses.format import _load_formats, _load_template
from rigour.addresses.normalize import _address_replacer
from rigour.names.org_types import _compare_replacer, _display_replacer
from rigour.names.org_types import _generic_replacer, replace_org_types_compare
from rigour.names.tagging import _get_org_tagger, _get_person_tagger


def reset_caches() -> None:
    """Reset LRU caches in the rigour module. This is meant to be used
    in long-lived processes to prevent memory expansion."""
    latinize_text.cache_clear()
    _ascii_text.cache_clear()
    levenshtein.cache_clear()
    normalize_name.cache_clear()
    dam_levenshtein.cache_clear()
    jaro_winkler.cache_clear()
    soundex.cache_clear()
    metaphone.cache_clear()
    can_latinize_cp.cache_clear()
    _load_formats.cache_clear()
    _load_template.cache_clear()
    _address_replacer.cache_clear()
    _compare_replacer.cache_clear()
    _display_replacer.cache_clear()
    _generic_replacer.cache_clear()
    replace_org_types_compare.cache_clear()
    _get_org_tagger.cache_clear()
    _get_person_tagger.cache_clear()
    get_index.cache_clear()
    _get_identifier_map.cache_clear()
    _get_territory_names.cache_clear()
    lookup_territory.cache_clear()
    gc.collect()
