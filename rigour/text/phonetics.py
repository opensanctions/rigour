from functools import lru_cache
from jellyfish import metaphone as metaphone_
from jellyfish import soundex as soundex_

from rigour.util import MEMO_LARGE


@lru_cache(maxsize=MEMO_LARGE)
def metaphone(token: str) -> str:
    """Get the metaphone phonetic representation of a token."""
    return metaphone_(token)


@lru_cache(maxsize=MEMO_LARGE)
def soundex(token: str) -> str:
    """Get the soundex phonetic representation of a token."""
    return soundex_(token)
