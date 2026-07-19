# This is a set of synonyms for pragmatic usage in NLP. It is based on
# working with Tesseract 3.04, but should be applicable elsewhere.
from functools import cache
from typing import Iterable


LANG_SYNONYMS = [
    ("srp", "hbs", "hrv", "bos"),
    ("sqi", "alb"),
    ("slk", "slo"),
    ("ron", "rum"),
    ("nld", "dut"),
    ("mya", "bur"),
    ("msa", "may"),
    ("mkd", "mac"),
    ("kat", "geo"),
    ("isl", "ice"),
    ("isl", "ice"),
    ("fre", "fra"),
    ("fas", "per"),
    ("eus", "baq"),
    ("ell", "gre"),
    ("ger", "deu"),
    ("wel", "cym"),
    ("chi_sim", "chi_tra", "chi", "zho"),
    ("ces", "cze"),
    ("bod", "tib"),
    ("aze_cyrl", "aze"),
    ("fil", "tgl"),
    ("nep", "npi"),
]

# "zxx" is the ISO 639-3 code for "no linguistic content"; "xzz" is a
# non-standard code kept for legacy compatibility.
NON_LANGS = {"mis", "mul", "und", "zxx", "xzz"}


@cache
def expand_synonyms(language: str) -> Iterable[str]:
    """Expand a language code into a set of codes."""
    for synonyms in LANG_SYNONYMS:
        if language in synonyms:
            return synonyms
    return [language]
