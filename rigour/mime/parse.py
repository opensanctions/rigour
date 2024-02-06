from email.message import EmailMessage
from typing import Any, Dict, Optional, Tuple
from normality import stringify
from normality.encoding import tidy_encoding

from rigour.mime.types import DEFAULT, LABELS
from rigour.mime.mappings import REPLACE


class MIMEType(object):
    __slots__ = ["family", "subtype", "params", "name", "normalized"]

    SEP = "/"

    def __init__(
        self,
        family: Optional[str],
        subtype: Optional[str],
        params: Optional[Dict[str, str]] = None,
    ):
        self.family = family
        self.subtype = subtype
        self.name: Optional[str] = None
        if self.family is not None and self.subtype is not None:
            self.name = self.SEP.join((self.family, self.subtype))
        self.normalized: Optional[str] = self.name
        if self.name in REPLACE:
            self.normalized = REPLACE.get(self.name, self.name)
        self.params: Dict[str, str] = params or {}

    @property
    def label(self) -> Optional[str]:
        if self.normalized in LABELS:
            return LABELS.get(self.normalized, self.normalized)
        if self.subtype is not None:
            label = self.subtype.lstrip("x")
            label = label.replace("-", " ")
            label = label.replace(".", " ")
            return label.strip()
        return None

    @property
    def charset(self) -> Optional[str]:
        charset = self.params.get("charset")
        if charset is None:
            return None
        return tidy_encoding(charset)

    @classmethod
    def split(cls, mime_type: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        if mime_type is None or cls.SEP not in mime_type:
            return None, None
        family, subtype = (p.strip() for p in mime_type.split(cls.SEP, 1))
        if len(family) == 0 or len(subtype) == 0:
            return None, None
        return family.lower(), subtype.lower()

    @classmethod
    def parse(
        cls, mime_type: Optional[str], default: Optional[str] = None
    ) -> "MIMEType":
        mime_type = stringify(mime_type)
        params = None
        if mime_type is not None:
            msg = EmailMessage()
            msg['content-type'] = mime_type
            mime_type = msg.get_content_type() if mime_type.count("/") == 1 else None
            params = msg['content-type'].params

        family, subtype = cls.split(mime_type)
        if family is None:
            family, subtype = cls.split(default)
        return cls(family, subtype, params=params)

    def __eq__(self, other: Any) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))

    def __str__(self) -> str:
        return self.name or DEFAULT

    def __repr__(self) -> str:
        return str(self)
