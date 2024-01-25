# This is a set of synonyms for pragmatic usage in NLP. It is based on
# working with Tesseract 3.04, but should be applicable elsewhere.
from functools import cache
from typing import Iterable


LANG_SYNONYMS = [
    ("srp", "hbs", "hrv", "bos"),
    ("sli", "alb"),
    ("slk", "slo"),
    ("ron", "rum"),
    ("nor", "non"),
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
    ("bur", "mya", "int", "tvn", "tco", "rki", "rmz"),
]


@cache
def expand_synonyms(language: str) -> Iterable[str]:
    """Expand a language code into a set of codes."""
    for synonyms in LANG_SYNONYMS:
        if language in synonyms:
            return synonyms
    return [language]
