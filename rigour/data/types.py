from typing import List, Optional, TypedDict


class OrgTypeSpec(TypedDict):
    display: Optional[str]
    compare: Optional[str]
    aliases: List[str]
