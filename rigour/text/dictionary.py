from typing import Dict, List


class Dictionary:
    """A class to manage a dictionary of words and their aliases. This is used to perform replacement
    on those aliases or the word itself in a text.
    """

    def __init__(self, mapping: Dict[str, str]):
        self.mapping = mapping

    def normalize(self, text: str) -> str:
        """Normalize a word before comparison."""
        return text.lower().strip()

    def replace(self, text: str) -> str:
        """Replace words in the text based on the dictionary mapping."""
        pass

    def remove(self, text: str) -> str:
        """Remove words mentioned (key or value) in the dictionary from the text."""
        pass

    def lookup(self, word: str) -> str:
        """Lookup a word in the dictionary and return its value form."""
        return self.mapping.get(word, word)
