from typing import Dict, List, Optional, Tuple
import ahocorasick
from normality import WS
import re

from rigour.names.symbol import Symbol
from rigour.text.dictionary import Scanner

# automaton = ahocorasick.Automaton()
# automaton.add_word(key, (idx, key))
# automaton.make_automaton()
# for end_index, (insert_order, original_value) in automaton.iter(haystack):
#     start_index = end_index - len(original_value) + 1
#     print((start_index, end_index, (insert_order, original_value)))
#     assert haystack[start_index:start_index + len(original_value)] == original_value


REGEX_TOKENS = re.compile(r"(?<!\w)(\w+)(?!\w)")


class Tagger(Scanner):
    """A class to manage a dictionary of words and their aliases. This is used to perform
    replacement on those aliases or the word itself in a text.
    """

    def __init__(self, mapping: Dict[str, List[Symbol]]) -> None:
        self.automaton = ahocorasick.Automaton()
        for form, symbols in mapping.items():
            self.automaton.add_word(form, (len(form), symbols))
        self.automaton.make_automaton()

    def __call__(self, text: Optional[str]) -> List[Tuple[str, Symbol]]:
        """Apply the tagger on a piece of pre-normalized text."""
        if text is None:
            return []
        results: List[Tuple[str, Symbol]] = []

        # Find boundaries of tokens in the text
        boundaries = set()
        for match in REGEX_TOKENS.finditer(text):
            boundaries.add(match.start())
            boundaries.add(match.end()-1)
        
        self.automaton.make_automaton()
        for end_index, (form_length, symbols) in self.automaton.iter(text):
            start_index = end_index - form_length + 1
            is_in_boundaries = start_index in boundaries and end_index in boundaries
            # Skip any matches that aren't along token boundaries
            if not is_in_boundaries:
                continue
            match = text[start_index:end_index + 1]
            for symbol in symbols:
                results.append((match, symbol))
            
        return results
