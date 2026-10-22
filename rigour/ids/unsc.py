import re
from typing import Optional

from rigour.ids.common import IdentifierFormat


class UNSC(IdentifierFormat):
    """UN Security Council Permanent Reference Number for sanctioned entities"""

    NAME = "unsc"
    TITLE = "UNSC"
    STRONG = True

    # UN Security Council Permanent Reference Number pattern:
    # Format: [REGIME_CODE][ENTITY_TYPE].[NUMBER]
    #
    # Components:
    #   [A-Z]{2,3}  - Regime code: 2-3 uppercase letters (e.g., QD, CD, CF)
    #   [ie]        - Entity type: 'i' for individual, 'e' for entity
    #   \.          - Literal dot separator
    #   \d{3,}      - Number: at least 3 digits (e.g., 002, 030, 123)
    #
    # Valid examples: QDi.002, QDe.123, CDi.030, CFi.001
    # See https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list for more examples
    UNSC_RE = re.compile(r"^[A-Z]{2,3}[ie]\.\d{3,}$")

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Determine if the given string is a valid UNSC permanent reference number."""
        if not value:
            return False
        return bool(cls.UNSC_RE.match(value))

    @classmethod
    def normalize(cls, value: str) -> Optional[str]:
        """Normalize the given string to a valid UNSC ID."""
        if not value:
            return None
        value = value.strip()
        if cls.is_valid(value):
            return value
        return None
