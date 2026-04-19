from functools import lru_cache

from rigour._core import metaphone as _metaphone
from rigour._core import soundex as _soundex
from rigour.util import MEMO_LARGE

__all__ = ["metaphone", "soundex"]


@lru_cache(maxsize=MEMO_LARGE)
def metaphone(token: str) -> str:
    """Get the metaphone phonetic representation of a token.

    Thin Python-level LRU cache over the Rust implementation. The cache pays
    off in matching workloads where the same name tokens recur across millions
    of entities — a cache hit skips the FFI crossing entirely.
    """
    return _metaphone(token)


@lru_cache(maxsize=MEMO_LARGE)
def soundex(token: str) -> str:
    """Get the soundex phonetic representation of a token.

    Thin Python-level LRU cache over the Rust implementation. Same rationale
    as metaphone above.
    """
    return _soundex(token)
