from typing import Optional
from rigour.data.langs.iso639 import ISO3_ALL


class LangStr(str):
    """A type of string that include language metadata. This is useful for handling multilingual content.

    The class does not override any operators and functions, which means they will behave like a regular string.
    """

    __slots__ = ("lang",)

    def __new__(cls, content: str, lang: Optional[str] = None) -> "LangStr":
        instance = str.__new__(cls, content)
        return instance

    def __init__(self, content: str, lang: Optional[str] = None) -> None:
        if lang is not None and lang not in ISO3_ALL:
            raise ValueError(f"Invalid ISO 639-3 language code: {lang}")
        self.lang = lang

    def __repr__(self) -> str:
        if self.lang is not None:
            return f'"{super().__str__()}"@{self.lang}'
        return super().__repr__()

    def __hash__(self) -> int:
        return hash((super().__str__(), self.lang))

    def __eq__(self, value: object) -> bool:
        try:
            return super().__eq__(value) and self.lang == value.lang  # type: ignore
        except AttributeError:
            return super().__eq__(value)

    def __ne__(self, value: object) -> bool:
        return not self.__eq__(value)
