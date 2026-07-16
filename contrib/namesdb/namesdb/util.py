import unicodedata
from functools import lru_cache
from typing import List, Optional
from normality.cleaning import remove_unsafe_chars

from rigour.names import is_name
from rigour.text.cleaning import remove_bracketed_text, remove_emoji
from rigour.text.scripts import is_modern_alphabet


def clean_form(form: str) -> Optional[str]:
    """Clean a name by removing leading and trailing whitespace."""
    form = remove_bracketed_text(form)
    form = remove_emoji(form)
    form = unicodedata.normalize("NFC", form.strip().lower())
    form = remove_unsafe_chars(form)
    if not is_name(form):
        return None
    if len(form) > 40:
        return None
    if is_modern_alphabet(form) and len(form) < 2:
        return None
    return form


@lru_cache(maxsize=1000)
def clean_wikidata_name(name: Optional[str]) -> List[str]:
    """Split and clean a raw Wikidata label/alias into storable name forms."""
    if name is None:
        return []
    names: List[str] = []
    for part in name.split("/"):
        # Check before clean_form strips the punctuation that marks
        # disambiguated labels such as "Alana (given name)".
        if "," in part or "(" in part or "=" in part or ":" in part:
            continue
        cleaned = clean_form(part)
        if cleaned is None:
            continue
        names.append(cleaned)
    return names
