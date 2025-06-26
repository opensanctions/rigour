from typing import Dict, List, Optional, Tuple
import hyperscan
import re

from rigour.names.symbol import Symbol


REGEX_TOKENS = re.compile(r"(?<!\w)(\w+)(?!\w)")


class Scanner:
    """Core class for scanning text for forms. It uses a regex pattern to match the list of
    given forms in the text, trying to match the longest form first."""

    def __init__(
        self,
        forms: List[str],
        ignore_case: bool = True,
    ) -> None:
        self.ignore_case = ignore_case
        self.forms = forms
    
    def compile(self):
        print("making forms")
        forms = [re.escape(form) for form in self.forms]
        print("forms", forms[:5])
        expressions = [br"%s" % form.encode("utf8") for form in forms]
        print("expressions", expressions[:5])
        flags = hyperscan.HS_FLAG_UTF8 | hyperscan.HS_FLAG_SOM_LEFTMOST
        if self.ignore_case:
            flags |= hyperscan.HS_FLAG_CASELESS
        flag_list = [flags] * len(expressions)
        ids = list(range(len(expressions)))
        db = hyperscan.Database()
        print("compiling hyperscan database")
        db.compile(expressions=expressions, ids=ids, flags=flag_list, elements=len(expressions))

        serialized = hyperscan.dumpb(db)
        with open('hs.db', 'wb') as f:
            f.write(serialized)
    
    def load(self):
        print("loading hyperscan database")
        with open('hs.db', 'rb') as f:
            serialized = f.read()
        self.db = hyperscan.loadb(serialized, hyperscan.HS_MODE_BLOCK)
        self.db.scratch = hyperscan.Scratch(self.db)
        print("loaded hyperscan database")


class Tagger(Scanner):
    """A class to manage a dictionary of words and their aliases. This is used to perform
    replacement on those aliases or the word itself in a text.
    """

    def __init__(self, mapping: Dict[str, List[Symbol]]) -> None:
        forms = list(mapping.keys())
        self.index: List[List[Symbol]] = list(mapping.values())
        super().__init__(forms, ignore_case=False)

    def __call__(self, text: Optional[str]) -> List[Tuple[str, Symbol]]:
        """Apply the tagger on a piece of pre-normalized text."""
        if text is None:
            return []
        symbols: List[Tuple[str, Symbol]] = []
        matches = []
        results = []

        # Find boundaries of tokens in the text
        boundaries = set()
        for match in REGEX_TOKENS.finditer(text):
            boundaries.add(match.start())
            boundaries.add(match.end())

        def match_handler(id, from_offset, to_offset, flags, context):
            matches.append((id, from_offset, to_offset))
            return 0

        self.db.scan(text.encode("utf8"), match_handler)

        for id, from_offset, to_offset in matches:
            if from_offset not in boundaries or to_offset not in boundaries:
                continue
            match = text[from_offset:to_offset]
            symbols = self.index[id]
            for symbol in symbols:
                results.append((match, symbol))
        return results

