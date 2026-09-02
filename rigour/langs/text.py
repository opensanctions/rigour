from typing import TypeVar

from rigour.data.langs.iso639 import ISO3_ALL

LangStrT = TypeVar("LangStrT", bound="LangStr")


class LangStr(str):
    """A string carrying an optional language tag.

    Use this to keep track of which language a piece of multilingual
    content is written in while still passing it around as a `str`.

    The language tag is part of the value's identity:

    * With no tag (`lang is None`), a `LangStr` is indistinguishable from
      its content string: it compares equal to the plain `str`, hashes the
      same, and deduplicates against it in sets and dict keys.
    * With a tag, a `LangStr` is a distinct value identified by the pair
      `(content, lang)`. It is not equal to the bare content string, nor
      to a `LangStr` with a different or missing tag, and it never
      deduplicates against them.

    Ordinary `str` methods (`.upper()`, slicing, concatenation, …) return
    plain `str` and drop the tag.

    Args:
        content: The text.
        lang: An ISO 639-3 language code, or `None` for untagged text.

    Raises:
        ValueError: If `lang` is not a known ISO 639-3 code.
    """

    __slots__ = ("lang",)

    def __new__(
        cls: type[LangStrT], content: str, lang: str | None = None
    ) -> LangStrT:
        return str.__new__(cls, content)

    def __init__(self, content: str, lang: str | None = None) -> None:
        if lang is not None and lang not in ISO3_ALL:
            raise ValueError(f"Invalid ISO 639-3 language code: {lang}")
        self.lang = lang

    def __repr__(self) -> str:
        if self.lang is not None:
            return f'"{super().__str__()}"@{self.lang}'
        return super().__repr__()

    def __hash__(self) -> int:
        if self.lang is None:
            return super().__hash__()
        return hash((super().__str__(), self.lang))

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, str):
            return NotImplemented
        other_lang = value.lang if isinstance(value, LangStr) else None
        return super().__eq__(value) and self.lang == other_lang

    def __ne__(self, value: object) -> bool:
        equal = self.__eq__(value)
        if equal is NotImplemented:
            return NotImplemented
        return not equal
