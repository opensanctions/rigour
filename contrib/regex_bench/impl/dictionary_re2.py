import re
import re2
from normality.constants import WS
from typing import Dict, List, Optional, Tuple

from rigour.names.symbol import Symbol


class Scanner:
    """Core class for scanning text for forms. It uses a regex pattern to match the list of
    given forms in the text, trying to match the longest form first."""

    def __init__(
        self,
        forms: List[str],
        ignore_case: bool = True,
    ) -> None:
        self.ignore_case = ignore_case
        # if ignore_case:
        #     forms = [form.lower() for form in forms]
        forms = sorted(set(forms), key=len, reverse=True)
        forms = [re2.escape(form) for form in forms]
        forms_regex = r"\b(%s)\b" % "|".join(forms)
        options = re2.Options()
        options.max_mem = 10000_000_000
        options.encoding = re2.Options.Encoding.UTF8
        if ignore_case:
            options.case_sensitive = False
        self.pattern = re2.compile(forms_regex, options)

    def extract(self, text: str) -> List[str]:
        """Extract forms from the text using the regex pattern. The text is assumed to have been
        normalized using the same procedure as the forms.

        Args:
            text (str): The text to be processed.

        Returns:
            List[str]: A list of matched forms.
        """
        matches = self.pattern.findall(text)
        if not len(matches):
            return []
        matches = [match for match in matches if len(match) > 0]
        return matches

    def remove(self, text: str, replacement: str = WS) -> str:
        """Remove forms from the text using the regex pattern. The text is assumed to have been
        normalized using the same procedure as the forms.

        Args:
            text (str): The text to be processed.
            replacement (str): The string to replace the matched forms with.

        Returns:
            str: The text with the matched forms replaced.
        """
        return self.pattern.sub(replacement, text)


class Tagger(Scanner):
    """A class to manage a dictionary of words and their aliases. This is used to perform
    replacement on those aliases or the word itself in a text.
    """

    def __init__(self, mapping: Dict[str, List[Symbol]]) -> None:
        forms = list(mapping.keys())
        super().__init__(forms, ignore_case=False)
        self.mapping = mapping

    def __call__(self, text: Optional[str]) -> List[Tuple[str, Symbol]]:
        """Apply the tagger on a piece of pre-normalized text."""
        if text is None:
            return []
        symbols: List[Tuple[str, Symbol]] = []
        for match in self.pattern.finditer(text):
            value = match.group(1)
            for symbol in self.mapping.get(value, []):
                symbols.append((value, symbol))

        for token in text.split(" "):
            if token in self.mapping:
                for symbol in self.mapping[token]:
                    if (token, symbol) not in symbols:
                        symbols.append((token, symbol))
        return symbols
