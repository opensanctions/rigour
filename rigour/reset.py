import gc

from rigour.addresses.format import _load_formats, _load_template
from rigour.addresses.normalize import _address_replacer
from rigour.names.prefix import (
    _obj_prefix_regex,
    _org_prefix_regex,
    _person_prefix_regex,
)
from rigour.names.split_phrases import _split_phrase_regex
from rigour.names.tokenize import normalize_name
from rigour.territories.lookup import (
    _get_identifier_map,
    _get_territory_names,
    lookup_territory,
)
from rigour.territories.territory import get_index
from rigour.text.distance import jaro_winkler, levenshtein
from rigour.text.phonetics import metaphone, soundex
from rigour.text.scripts import codepoint_script

# Tagger caches live Rust-side, keyed on (TaggerKind, Normalize,
# Cleanup) in a process-lifetime RwLock<HashMap>. There's no
# Python-side handle to reset; the built automata stay until process
# exit. Same shape as the org_types Replacer cache.


def reset_caches() -> None:
    """Reset LRU caches in the rigour module. This is meant to be used
    in long-lived processes to prevent memory expansion."""
    levenshtein.cache_clear()
    normalize_name.cache_clear()
    jaro_winkler.cache_clear()
    soundex.cache_clear()
    metaphone.cache_clear()
    codepoint_script.cache_clear()
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
