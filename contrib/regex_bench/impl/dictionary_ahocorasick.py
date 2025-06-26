from typing import Dict, List, Optional, Tuple
import ahocorasick_rs
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
        self.symbols = list(mapping.values())
        self.automaton = ahocorasick_rs.AhoCorasick(mapping.keys())

    def __call__(self, text: Optional[str]) -> List[Tuple[str, Symbol]]:
        """Apply the tagger on a piece of pre-normalized text."""
        if text is None:
            return []
        results: List[Tuple[str, Symbol]] = []

        # Find boundaries of tokens in the text
        boundaries = set()
        for match in REGEX_TOKENS.finditer(text):
            boundaries.add(match.start())
            boundaries.add(match.end())

        for pattern_index, start, end in self.automaton.find_matches_as_indexes(
            text, overlapping=True
        ):
            # Skip any matches that aren't along token boundaries
            if start not in boundaries or end not in boundaries:
                continue
            match = text[start:end]
            for symbol in self.symbols[pattern_index]:
                results.append((match, symbol))

        return results
