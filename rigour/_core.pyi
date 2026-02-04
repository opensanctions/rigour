"""Type stubs for the rigour._core Rust module.

This module contains performance-critical implementations written in Rust
and exposed to Python via PyO3.
"""

def normalize_address(
    address: str,
    latinize: bool = False,
    min_length: int = 4,
) -> str | None:
    """Normalize an address string for comparison and deduplication.

    Args:
        address: The address string to normalize
        latinize: Whether to transliterate to ASCII/Latin script
        min_length: Minimum length for the normalized result

    Returns:
        Normalized address string, or None if too short
    """
    ...

def ascii_text(text: str) -> str:
    """Transliterate text to ASCII using ICU.

    Args:
        text: The text to transliterate

    Returns:
        ASCII-transliterated text
    """
    ...

def tokenize_name(text: str, token_min_length: int = 1) -> list[str]:
    """Split a person or entity's name into name parts.

    Args:
        text: The name string to tokenize
        token_min_length: Minimum length for tokens (default: 1)

    Returns:
        List of name part strings
    """
    ...

def prenormalize_name(name: str) -> str:
    """Prepare a name for tokenization and matching.

    Applies Unicode case folding for caseless comparison.

    Args:
        name: The name string to prenormalize

    Returns:
        Casefolded name string
    """
    ...

def normalize_name(name: str, sep: str = " ") -> str | None:
    """Normalize a name for tokenization and matching.

    Args:
        name: The name string to normalize
        sep: Token separator (default: " ")

    Returns:
        Normalized name string, or None if empty
    """
    ...
