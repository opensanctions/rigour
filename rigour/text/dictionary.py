import re
from normality.constants import WS
from typing import Callable, Dict, List, Optional

Normalizer = Callable[[Optional[str]], Optional[str]]


def noop_normalizer(text: Optional[str]) -> Optional[str]:
    """A no-op normalizer that returns the text unchanged."""
    if text is None:
        return None
    text = text.strip()
    if len(text) == 0:
        return None
    return text


class Scanner:
    """Core class for scanning text for forms. It uses a regex pattern to match the list of
    given forms in the text, trying to match the longest form first."""

    # Part of the reason for making this a re-usable class is to allow us to play
    # with google's re2, which use a finite state machine to match regexes and might
    # be faster than the python regex engine.
    # cf. https://github.com/google/re2

    def __init__(
        self,
        forms: List[str],
        ignore_case: bool = True,
    ) -> None:
        self.ignore_case = ignore_case
        if ignore_case:
            forms = [form.lower() for form in forms]
        forms = sorted(set(forms), key=len, reverse=True)
        forms = [re.escape(form) for form in forms]
        forms_regex = "\\b(%s)\\b" % "|".join(forms)
        flags = re.U | re.I if ignore_case else re.U
        self.pattern = re.compile(forms_regex, flags)

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


class Replacer(Scanner):
    """A class to manage a dictionary of words and their aliases. This is used to perform replacement
    on those aliases or the word itself in a text.
    """

    def __init__(
        self,
        mapping: Dict[str, str],
        ignore_case: bool = True,
    ) -> None:
        forms = list(mapping.keys())
        super().__init__(forms, ignore_case=ignore_case)
        if ignore_case:
            mapping = {k.lower(): v for k, v in mapping.items()}
        self.mapping = mapping

    def _get(self, match: re.Match[str]) -> str:
        """Internal: given a match, return the replacement value. Called by the regex."""
        value = match.group(1)
        lookup = value.lower() if self.ignore_case else value
        return self.mapping.get(lookup, value)

    def __call__(self, text: Optional[str]) -> Optional[str]:
        """Apply the replacer on a piece of pre-normalized text."""
        if text is None:
            return None
        return self.pattern.sub(self._get, text)
