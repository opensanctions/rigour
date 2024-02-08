from typing import Optional

from rigour.mime.parse import MIMEType
from rigour.mime.types import DEFAULT, PLAIN


def parse_mimetype(text: Optional[str], default: str = DEFAULT) -> MIMEType:
    """Parse a MIME type into a structured object."""
    return MIMEType.parse(text, default=default)


def normalize_mimetype(text: Optional[str], default: str = DEFAULT) -> str:
    """Normalize the spelling of a MIME type."""
    return parse_mimetype(text, default=default).normalized or default


def useful_mimetype(text: Optional[str]) -> bool:
    """Check to see if the given mime type is a MIME type
    which is useful in terms of how to treat this file.
    """
    mimetype = normalize_mimetype(text)
    return mimetype not in [DEFAULT, PLAIN, None]
