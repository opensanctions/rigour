import gc

from rigour.text.distance import levenshtein, dam_levenshtein, jaro_winkler
from rigour.text.phonetics import soundex, metaphone
from rigour.territories.territory import get_index
from rigour.territories.lookup import lookup_territory
from rigour.territories.lookup import _get_identifier_map, _get_territory_names
from rigour.text.scripts import can_latinize_cp
from rigour.names.tokenize import _normalize_name
from rigour.names.prefix import (
    _person_prefix_regex,
    _org_prefix_regex,
    _obj_prefix_regex,
)
from rigour.names.split_phrases import _split_phrase_regex
from rigour.addresses.format import _load_formats, _load_template
from rigour.addresses.normalize import _address_replacer
# Tagger caches live Rust-side, keyed on (TaggerKind, Normalize,
# Cleanup) in a process-lifetime RwLock<HashMap>. There's no
# Python-side handle to reset; the built automata stay until process
# exit. Same shape as the org_types Replacer cache.


def reset_caches() -> None:
    """Reset LRU caches in the rigour module. This is meant to be used
    in long-lived processes to prevent memory expansion."""
    levenshtein.cache_clear()
    _normalize_name.cache_clear()
    dam_levenshtein.cache_clear()
    jaro_winkler.cache_clear()
    soundex.cache_clear()
    metaphone.cache_clear()
    can_latinize_cp.cache_clear()
    _load_formats.cache_clear()
    _load_template.cache_clear()
    _address_replacer.cache_clear()
    _person_prefix_regex.cache_clear()
    _org_prefix_regex.cache_clear()
    _obj_prefix_regex.cache_clear()
    _split_phrase_regex.cache_clear()
    get_index.cache_clear()
    _get_identifier_map.cache_clear()
    _get_territory_names.cache_clear()
    lookup_territory.cache_clear()
    gc.collect()
