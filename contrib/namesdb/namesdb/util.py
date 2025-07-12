from typing import Optional
import unicodedata

from rigour.names import is_name
from rigour.text.cleaning import remove_bracketed_text, remove_emoji
from rigour.text.scripts import is_modern_alphabet


def clean_form(form: str) -> Optional[str]:
    """Clean a name by removing leading and trailing whitespace."""
    form = remove_bracketed_text(form)
    form = remove_emoji(form)
    form = unicodedata.normalize("NFC", form.strip().lower())
    if not is_name(form):
        return None
    if len(form) > 40:
        return None
    if is_modern_alphabet(form) and len(form) < 2:
        return None
    return form
