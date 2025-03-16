"""
# Language code handling

This library helps to normalise the ISO 639 codes used to describe languages from
two-letter codes to three letters, and vice versa.

```python
import rigour.langs as languagecodes

assert 'eng' == languagecodes.iso_639_alpha3('en')
assert 'eng' == languagecodes.iso_639_alpha3('ENG ')
assert 'en' == languagecodes.iso_639_alpha2('ENG ')
```

Uses data from: https://iso639-3.sil.org/
See also: https://www.loc.gov/standards/iso639-2/php/code_list.php
"""

from typing import Iterable, Optional, Set
from banal import ensure_list

from rigour.data.langs.iso639 import ISO3_ALL, ISO2_MAP, ISO3_MAP
from rigour.langs.synonyms import expand_synonyms, LANG_REWRITE
from rigour.langs.util import normalize_code
from rigour.env import PREFERRED_LANG as PREFERRED_LANG_

# The world is a cruel and dark place so here we're picking a list of
# languages that are most widely readable. The bias is towards European
# languages using a latin script.
# https://en.wikipedia.org/wiki/List_of_languages_by_number_of_native_speakers
PREFERRED_LANG = PREFERRED_LANG_  # env: RR_PREFERRED_LANG/eng
PREFFERED_LANGS = [
    "eng",
    "spa",
    "fra",
    "por",
    "deu",
    "nld",
    "ita",
    "tur",
    "pol",
    "ron",
    "ces",
    "srp",
    "hrv",
    "dan",
    "nor",
    "rus",
    "ukr",
    "ara",
    "fas",
    "urd",
    "zho",
]


def iso_639_alpha3(code: str) -> Optional[str]:
    """Convert a given language identifier into an ISO 639 Part 2 code, such
    as "eng" or "deu". This will accept language codes in the two- or three-
    letter format, and some language names. If the given string cannot be
    converted, ``None`` will be returned.

    >>> iso_639_alpha3('en')
    'eng'
    """
    norm = normalize_code(code)
    if norm is not None:
        norm = ISO3_MAP.get(norm, norm)
    if norm is not None:
        norm = LANG_REWRITE.get(norm, norm)
    if norm not in ISO3_ALL:
        return None
    return norm


def iso_639_alpha2(code: str) -> Optional[str]:
    """Convert a language identifier to an ISO 639 Part 1 code, such as "en"
    or "de". For languages which do not have a two-letter identifier, or
    invalid language codes, ``None`` will be returned.
    """
    alpha3 = iso_639_alpha3(code)
    if alpha3 is None:
        return None
    return ISO2_MAP.get(alpha3)


def list_to_alpha3(languages: Iterable[str], synonyms: bool = True) -> Set[str]:
    """Parse all the language codes in a given list into ISO 639 Part 2 codes
    and optionally expand them with synonyms (i.e. other names for the same
    language)."""
    codes = set([])
    for language in ensure_list(languages):
        code = iso_639_alpha3(language)
        if code is None:
            continue
        codes.add(code)
        if synonyms:
            codes.update(expand_synonyms(code))
    return codes
