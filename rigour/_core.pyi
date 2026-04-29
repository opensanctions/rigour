def metaphone(token: str) -> str: ...
def soundex(token: str) -> str: ...
def codepoint_script(cp: int) -> str | None: ...
def text_scripts(text: str) -> set[str]: ...
def common_scripts(a: str, b: str) -> set[str]: ...
def should_ascii(text: str) -> bool: ...
def maybe_ascii(text: str, drop: bool = False) -> str: ...
def tokenize_name(text: str, token_min_length: int = 1) -> list[str]: ...
def _normalize(text: str, flags: int, cleanup: int) -> str | None: ...
def string_number(text: str) -> float | None: ...
def pick_name(names: list[str]) -> str | None: ...
def pick_case(names: list[str]) -> str | None: ...
def reduce_names(names: list[str]) -> list[str]: ...
def replace_org_types_compare(text: str, flags: int, cleanup: int, generic: bool) -> str: ...
def replace_org_types_display(text: str, flags: int, cleanup: int) -> str: ...
def remove_org_types(text: str, flags: int, cleanup: int, replacement: str) -> str: ...
def extract_org_types(
    text: str, flags: int, cleanup: int, generic: bool
) -> list[tuple[str, str]]: ...


# Resource accessors — plain data returners read once at import time
# by Python consumers.
def stopwords_list() -> list[str]: ...
def nullwords_list() -> list[str]: ...
def nullplaces_list() -> list[str]: ...
def person_name_prefixes_list() -> list[str]: ...
def org_name_prefixes_list() -> list[str]: ...
def obj_name_prefixes_list() -> list[str]: ...
def name_split_phrases_list() -> list[str]: ...
def generic_person_names_list() -> list[str]: ...
def ordinals_dict() -> dict[int, list[str]]: ...
def territories_jsonl() -> str: ...


class SymbolCategory:
    """Sealed enum of symbol categories. See
    [rigour.text.normalize][] for related flag-based design.
    """

    ORG_CLASS: "SymbolCategory"
    SYMBOL: "SymbolCategory"
    DOMAIN: "SymbolCategory"
    INITIAL: "SymbolCategory"
    NAME: "SymbolCategory"
    NICK: "SymbolCategory"
    NUMERIC: "SymbolCategory"
    LOCATION: "SymbolCategory"
    PHONETIC: "SymbolCategory"

    @property
    def value(self) -> str:
        """Short serialisation key (e.g. ``"ORGCLS"``, ``"NUM"``)."""
        ...


class Symbol:
    """A semantic interpretation applied to one or more parts of a name.

    Rust-backed struct holding a category and an interned string id.
    Equal Symbols share one underlying `Arc<str>` allocation.
    """

    # `Category` is re-exported from rigour/names/symbol.py as an
    # alias for `SymbolCategory` — preserves the pre-port nested-
    # class access pattern `Symbol.Category.ORG_CLASS`. Declared here
    # so mypy knows about it.
    Category: type[SymbolCategory]

    category: SymbolCategory

    def __init__(self, category: SymbolCategory, id: str | int) -> None:
        """`id` is decimal-stringified if passed as int."""

    @property
    def id(self) -> str:
        """The interned id string."""
        ...


class NameTypeTag:
    """Metadata on what sort of object is described by a name."""

    UNK: "NameTypeTag"
    ENT: "NameTypeTag"
    PER: "NameTypeTag"
    ORG: "NameTypeTag"
    OBJ: "NameTypeTag"

    @property
    def value(self) -> str: ...


class NamePartTag:
    """Within a name, identify name-part types."""

    UNSET: "NamePartTag"
    AMBIGUOUS: "NamePartTag"
    TITLE: "NamePartTag"
    GIVEN: "NamePartTag"
    MIDDLE: "NamePartTag"
    FAMILY: "NamePartTag"
    TRIBAL: "NamePartTag"
    PATRONYMIC: "NamePartTag"
    MATRONYMIC: "NamePartTag"
    HONORIFIC: "NamePartTag"
    SUFFIX: "NamePartTag"
    NICK: "NamePartTag"
    STOP: "NamePartTag"
    NUM: "NamePartTag"
    LEGAL: "NamePartTag"

    @property
    def value(self) -> str: ...

    def can_match(self, other: "NamePartTag") -> bool: ...


class NamePart:
    """A tagged component of a name. See rigour/names/part.py."""

    form: str
    index: int
    tag: NamePartTag
    latinize: bool
    numeric: bool
    ascii: str | None
    integer: int | None
    comparable: str
    metaphone: str | None

    def __init__(
        self,
        form: str,
        index: int,
        tag: NamePartTag = ...,
        phonetics: bool = True,
    ) -> None: ...

    def __len__(self) -> int: ...

    @classmethod
    def tag_sort(cls, parts: list["NamePart"]) -> list["NamePart"]: ...


class Span:
    """A set of parts of a name tagged with a Symbol."""

    parts: tuple[NamePart, ...]
    symbol: Symbol
    comparable: str

    def __init__(self, parts: list[NamePart], symbol: Symbol) -> None: ...

    def __len__(self) -> int: ...


class Name:
    """A name — top of the rigour.names object graph."""

    original: str
    form: str
    tag: NameTypeTag
    parts: tuple[NamePart, ...]
    spans: list[Span]
    comparable: str
    norm_form: str

    def __init__(
        self,
        original: str,
        form: str | None = None,
        tag: NameTypeTag = ...,
        phonetics: bool = True,
    ) -> None: ...

    @property
    def symbols(self) -> set[Symbol]: ...

    def tag_text(
        self, text: str, tag: NamePartTag, max_matches: int = 1
    ) -> None: ...

    def apply_phrase(self, phrase: str, symbol: Symbol) -> None: ...

    def apply_part(self, part: NamePart, symbol: Symbol) -> None: ...

    def contains(self, other: "Name") -> bool: ...

    @classmethod
    def consolidate_names(cls, names: "object") -> set["Name"]: ...


def analyze_names(
    type_tag: NameTypeTag,
    names: list[str],
    part_tags: dict[NamePartTag, list[str]] | None = None,
    *,
    infer_initials: bool = False,
    symbols: bool = True,
    phonetics: bool = True,
    numerics: bool = True,
    consolidate: bool = True,
    rewrite: bool = True,
) -> set[Name]: ...


def align_person_name_order(
    left: list[NamePart],
    right: list[NamePart],
) -> tuple[list[NamePart], list[NamePart]]: ...


class PairedEdge:
    """Rust-side representation of one paired span in a pairing.

    Prefer the higher-level `rigour.names.symbol.pair_symbols`
    wrapper, which returns `SymbolEdge` dataclasses with resolved
    `NamePart` references; this pyclass exposes raw part indices
    (`int`s) and is primarily useful when calling the Rust entry
    point directly.
    """

    @property
    def query_parts(self) -> tuple[int, ...]: ...
    @property
    def result_parts(self) -> tuple[int, ...]: ...
    @property
    def symbol(self) -> Symbol: ...


def pair_symbols(query: Name, result: Name) -> list[tuple[PairedEdge, ...]]: ...


class Comparison:
    """One residue-distance cluster.

    Either a paired record (both `qps` and `rps` non-empty) or a solo
    record (one side empty, the other a single part). Returned by
    [compare_parts][rigour._core.compare_parts].
    """

    qps: tuple[NamePart, ...]
    rps: tuple[NamePart, ...]
    score: float


def compare_parts(
    qry: list[NamePart],
    res: list[NamePart],
    fuzzy_tolerance: float = 1.0,
) -> list[Comparison]: ...
