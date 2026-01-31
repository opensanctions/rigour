from typing import List, Optional
from normality.constants import WS

from rigour._core import (
    tokenize_name as _tokenize_name_core,
    prenormalize_name as _prenormalize_name_core,
    normalize_name as _normalize_name_core,
)


def tokenize_name(text: str, token_min_length: int = 1) -> List[str]:
    """Split a person or entity's name into name parts.

    This function is implemented in Rust for performance.

    Args:
        text: The name string to tokenize
        token_min_length: Minimum length for tokens (default: 1)

    Returns:
        List of name part strings

    Examples:
        >>> tokenize_name("John Smith")
        ['John', 'Smith']
        >>> tokenize_name("O'Brien")
        ['OBrien']
    """
    return _tokenize_name_core(text, token_min_length)


def prenormalize_name(name: Optional[str]) -> str:
    """Prepare a name for tokenization and matching.

    This function is implemented in Rust for performance.

    Args:
        name: The name string to prenormalize (None returns empty string)

    Returns:
        Prenormalized name string (casefolded)

    Examples:
        >>> prenormalize_name("John SMITH")
        'john smith'
        >>> prenormalize_name("MÜLLER")
        'müller'
        >>> prenormalize_name(None)
        ''
    """
    if name is None:
        return ""
    return _prenormalize_name_core(name)


def normalize_name(name: Optional[str], sep: str = WS) -> Optional[str]:
    """Normalize a name for tokenization and matching.

    This function is implemented in Rust for performance.

    Args:
        name: The name string to normalize
        sep: Token separator (default: " ")

    Returns:
        Normalized name string, or None if empty

    Examples:
        >>> normalize_name("John SMITH")
        'john smith'
        >>> normalize_name("O'Brien")
        'obrien'
        >>> normalize_name(None)
        None
    """
    if name is None:
        return None
    return _normalize_name_core(name, sep)
