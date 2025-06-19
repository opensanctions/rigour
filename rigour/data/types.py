from typing import List, Optional, TypedDict


class OrgTypeSpec(TypedDict, total=False):
    display: Optional[str]
    compare: Optional[str]
    generic: Optional[str]
    aliases: List[str]
