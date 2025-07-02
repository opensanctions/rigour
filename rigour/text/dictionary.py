import re
from typing import Callable, Dict, List, Optional, Set, Tuple

from normality.constants import WS
from ahocorasick_rs import AhoCorasick
from abc import ABC, abstractmethod

Normalizer = Callable[[Optional[str]], Optional[str]]
REGEX_TOKENS = re.compile(r"(?<!\w)([\w.-]+)(?!\w)")


def noop_normalizer(text: Optional[str]) -> Optional[str]:
    """A no-op normalizer that returns the text unchanged."""
    if text is None:
        return None
    text = text.strip()
    if len(text) == 0:
        return None
    return text


class Scanner(ABC):
    """Abstract base class for scanners."""

    @abstractmethod
    def __init__(self, forms: List[str], ignore_case: bool = True) -> None:
        """Initialize the scanner with a list of forms."""
        pass

    @abstractmethod
    def extract(self, text: str) -> List[str]:
        """Extract forms from the text."""
        pass

    @abstractmethod
    def remove(self, text: str, replacement: str = WS) -> str:
        """Remove forms from the text."""
        pass


class Replacer(Scanner):
    """Abstract base class for replacers."""

    mapping: Dict[str, str]

    @abstractmethod
    def __init__(self, mapping: Dict[str, str], ignore_case: bool = True) -> None:
        """Initialize the replacer with a mapping of forms to their replacements."""
        pass

    @abstractmethod
    def __call__(self, text: Optional[str]) -> Optional[str]:
        """Apply the replacer on a piece of text."""
        pass


class REScanner(Scanner):
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
        # if ignore_case:
        #     forms = [form.lower() for form in forms]
        forms = sorted(set(forms), key=len, reverse=True)
        forms = [re.escape(form) for form in forms]
        forms_regex = r"(?<!\w)(%s)(?!\w)" % "|".join(forms)
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


class REReplacer(REScanner, Replacer):
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


def word_boundary_matches(
    text: str, matches: List[Tuple[int, int, int]]
) -> List[Tuple[int, int, int]]:
    """Keep only matches starting and ending on some token boundary in the text"""
    # Find boundaries of tokens in the text
    boundaries = set()
    for word_match in REGEX_TOKENS.finditer(text):
        boundaries.add(word_match.start())
        boundaries.add(word_match.end())

    token_matches: List[Tuple[int, int, int]] = []
    for pattern_index, start, end in matches:
        # Skip any matches that aren't along token boundaries
        if start not in boundaries or end not in boundaries:
            continue
        token_matches.append((pattern_index, start, end))
    return token_matches


def non_overlapping(matches: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    """Keep only non-overlapping matches in pattern index order."""
    non_overlapping_matches: List[Tuple[int, int, int]] = []
    covered: Set[int] = set()
    for pattern_index, start, end in sorted(matches, key=lambda x: x[0]):
        # Check if this match overlaps with any previously selected match
        if any(pos in covered for pos in range(start, end)):
            continue
        non_overlapping_matches.append((pattern_index, start, end))
        covered.update(range(start, end))
    return non_overlapping_matches


class AhoCorScanner(Scanner):
    def __init__(self, forms: List[str], ignore_case: bool = True) -> None:
        self.ignore_case = ignore_case
        case_forms = []
        for form in forms:
            case_forms.append(form.lower() if ignore_case else form)
        self.automaton = AhoCorasick(case_forms)

    def _match(self, text: str) -> List[Tuple[int, int, int]]:
        """Find all the non-overlapping matches, preferring earlier patterns over later ones."""
        if self.ignore_case:
            text = text.lower()

        # We want all matches from Aho Corasick, including overlapping, so that when we remove
        # matches that didn't fall on token boundaries, we're left with matches that might
        # have come later in form order than others that didn't fall on token boundaries.
        matches = self.automaton.find_matches_as_indexes(text, overlapping=True)
        matches = word_boundary_matches(text, matches)
        # We then need to get rid of the remaining matches that do overlap.
        matches = non_overlapping(matches)
        return matches

    def extract(self, text: str) -> List[str]:
        """Extract all matching forms from the text. The text is assumed to have been
        normalized using the same procedure as the forms.

        Args:
            text (str): The text to be processed.

        Returns:
            List[str]: A list of matched forms.
        """
        matches = []
        for _pattern_index, start, end in self._match(text):
            matches.append(text[start:end])
        return matches

    def remove(self, text: str, replacement: str = WS) -> str:
        original_text = text
        segments = []
        ranges = []
        for pattern_index, start, end in self._match(text):
            ranges.append((start, end))
        if not ranges:
            return text
        ranges.sort(key=lambda x: x[0])
        # add replacements in place of matches, and add the original text between matches
        for i, (start, end) in enumerate(ranges):
            # Add the original text between the previous match and the current
            previous_range_end = ranges[i - 1][1] if i > 0 else 0
            segments.append(original_text[previous_range_end:start])
            # Add the replacement for the current match
            segments.append(replacement)
        # Add the remaining original text after the last match
        segments.append(original_text[ranges[-1][1] :])

        return "".join(segments)


class AhoCorReplacer(AhoCorScanner, Replacer):
    """A class to manage a dictionary of words and their aliases using Aho-Corasick algorithm.
    This is used to perform replacement on those aliases or the word itself in a text.
    """

    def __init__(self, mapping: Dict[str, str], ignore_case: bool = True) -> None:
        self.mapping = mapping
        self.replacements = []
        forms = []
        for k, v in mapping.items():
            # Skip empty keys
            if not k:
                continue
            self.replacements.append(v)
            forms.append(k)
        super().__init__(forms, ignore_case=ignore_case)

    def __call__(self, text: Optional[str]) -> Optional[str]:
        """Apply the replacer on a piece of pre-normalized text."""
        if text is None:
            return None
        for pattern_index, start, end in self._match(text):
            replacement = self.replacements[pattern_index]
            text = text[:start] + replacement + text[end:]

        return text
