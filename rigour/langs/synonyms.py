# This is a set of synonyms for pragmatic usage in NLP. It is based on
# working with Tesseract 3.04, but should be applicable elsewhere.
from functools import cache
from typing import Dict, Iterable, Optional


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

LANG_REWRITE: Dict[str, Optional[str]] = {
    "arb": "ara",
    "arz": "ara",
    "apc": "ara",
    "acm": "ara",
    "nno": "nor",
    "non": "nor",
    "bur": "mya",
    "cze": "ces",
    "ger": "deu",
    "gre": "ell",
    "per": "fas",
    "rum": "ron",
    "fre": "fra",
    "geo": "kat",
    "arm": "hye",
    "ice": "isl",
    "mac": "mkd",
    "chi": "zho",
    "chi_sim": "zho",
    "chi_tra": "zho",
    "aze_cyrl": "aze",
    "may": "msa",
    "dut": "nld",
    "slo": "slk",
    "alb": "sqi",
    "mis": None,
    "mul": None,
    "und": None,
    "xzz": None,
}


@cache
def expand_synonyms(language: str) -> Iterable[str]:
    """Expand a language code into a set of codes."""
    for synonyms in LANG_SYNONYMS:
        if language in synonyms:
            return synonyms
    return [language]
