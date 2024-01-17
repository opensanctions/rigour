import re
from typing import Optional

from rigour.ids.common import IdentifierFormat

OGRN_RE = re.compile(r"\b(\d{13}|\d{15})\b")


class OGRN(IdentifierFormat):
    """Primary State Registration Number (Russian company registration)."""

    TITLE: str = "OGRN"

    # cf. https://docs.trellix.com/de-DE/bundle/data-loss-prevention-11.10.x-classification-definitions-reference-guide/page/GUID-945B4343-861E-4A57-8E60-8B6028871BA1.html

    @classmethod
    def is_valid(cls, text: str) -> bool:
        """Determine if the given string is a valid OGRN."""
        return OGRN_RE.match(text) is not None

    @classmethod
    def normalize(cls, text: str) -> Optional[str]:
        """Normalize the given string to a valid OGRN."""
        match = OGRN_RE.search(text)
        if match is None:
            return None
        return match.group(1)
