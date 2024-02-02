from functools import lru_cache
from jellyfish import metaphone as metaphone_
from jellyfish import soundex as soundex_


@lru_cache(maxsize=1024)
def metaphone(token: str) -> str:
    """Get the metaphone phonetic representation of a token."""
    return metaphone_(token)


@lru_cache(maxsize=1024)
def soundex(token: str) -> str:
    """Get the soundex phonetic representation of a token."""
    return soundex_(token)