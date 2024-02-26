from typing import Optional

from rigour.countries.territory import World, Territory

__all__ = ["world", "get_territory"]

world = World()

def get_territory(code: str) -> Optional[Territory]:
    """Get a territory object for the given code.
    
    Args:
        code: Country, territory or jurisdiction code.
        
    Returns:
        A territory object.
    """
    if not world.has(code):
        return None
    return world.get(code)