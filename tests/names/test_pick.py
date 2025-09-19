import pytest
from rigour.langs import LangStr, PREFERRED_LANG
from rigour.names.pick import (
    pick_name,
    pick_lang_name,
    levenshtein_pick,
    pick_case,
    reduce_names,
)

PUTIN = [
    "Vladimir Vladimirovich Putin",
    "PUTIN, Vladimir Vladimirovich",
    "Vladimir Vladimirovitj PUTIN",
    "Владимир Владимирович Путин",
    "Vladimir Putin",
    "Vladimir Vladimirovich PUTIN",
    "ПУТІН Володимир Володимирович",
    "ウラジーミル・プーチン",
    "PUTIN Vladimir Vladimirovich",
    "Putin Vladimir Vladimirovich",
    "ПУТИН Владимир Владимирович",
    "Влади́мир Влади́мирович ПУ́ТИН",
    "Путін Володимир Володимирович",
    "Vladimir Vladimirovich POUTINE",
]

MITCH = [
    "Mitch McConnell",
    "Mičs Makonels",
    "Μιτς ΜακΚόννελ",
    "Митч Макконнелл",
    "Мич Макконъл",
    "Мич Маконел",
    "Мітч Макконнелл",
    "Միթչել Մակքոնել",
    "מיץ' מקונל",
    "ميتش ماكونيل",
    "میچ مکانل",
    "मिच मक्कोनेल",
    "ミッチ・マコーネル",
    "米奇·麥康諾",
    "미치 매코널",
]

TAGGED = [
    LangStr("Mitch McConnell", lang=PREFERRED_LANG),
    LangStr("Mitch McConne", lang=None),
    LangStr("Mitch McConne", lang=None),
    LangStr("Mitch McConne", lang=None),
    LangStr("Mitch McConne", lang=None),
    LangStr("Mitch McConne", lang=None),
    LangStr("Mitch McConne", lang=None),
    LangStr("Митч Макконнелл", lang="rus"),
    LangStr("میتچ ماکونل", lang="ara"),
    LangStr("ミッチ・マコーネル", lang="jpn"),
    LangStr("米奇·麥康諾", lang="zho"),
    LangStr("미치 매코널", lang="kor"),
]


def test_pick_nothing():
    name = pick_name([])
    assert name is None, "Expected None for empty list"
    name = pick_name([""])
    assert name is None, "Expected None for empty string"


def test_pick_mitch():
    name = pick_name(MITCH)
    assert name is not None
    assert name == "Mitch McConnell", name


def test_pick_putin():
    name = pick_name(PUTIN)
    assert name is not None
    assert name.lower().endswith("putin"), name


def test_pick_latin():
    names = [
        "Vladimir Vladimirovich Putin",
        "Владимир Владимирович Путин",
        "Владимир Владимирович Путин",
    ]
    name = pick_name(names)
    assert name is not None
    assert "Putin" in name, name


def test_pick_titlecase():
    names = [
        "Vladimir Vladimirovich Putin",
        "Vladimir Vladimirovich PUTIN",
        "Vladimir Vladimirovich PUTIN",
    ]
    name = pick_name(names)
    assert name is not None
    assert "Putin" in name, names


def test_pick_weird():
    values = ["Banana", "banana", "nanana", "Batman"]
    assert pick_name(values) == "Banana"
    assert pick_name(["Banana"]) == "Banana"
    assert pick_name([]) is None
    values = ["Robert Smith", "Rob Smith", "Robert SMITH"]
    assert pick_name(values) == "Robert Smith"

    # handle dirty edgecases
    values = ["", "PETER", "Peter"]
    assert pick_name(values) == "Peter"


def test_levenshtein_pick():
    assert levenshtein_pick([], {}) == []
    names = [
        "Vladimir Vladimirovich Putin",
        "Vladimir Vladimirovich PUTN",
        "Vladimir Vladimirovich PUTINY",
        "Vladimir Vladimirovich PUTIN",
    ]
    assert levenshtein_pick(names, {})[0] == "Vladimir Vladimirovich PUTIN"
    weights = {"Vladimir Vladimirovich Putin": 3.0}
    assert levenshtein_pick(names, weights)[0] == "Vladimir Vladimirovich Putin"


def test_pick_lang_name():
    assert pick_lang_name(TAGGED) == "Mitch McConnell"


def test_pick_case():
    cases = [
        "Vladimir Putin",
        "Vladimir PUTIN",
        "VLADIMIR PUTIN",
    ]
    assert pick_case(cases) == "Vladimir Putin"
    with pytest.raises(ValueError):
        pick_case([])
    assert pick_case(["VLADIMIR PUTIN"]) == "VLADIMIR PUTIN"


def test_pick_case_stoesslein():
    names = [
        "Stefan Stösslein",
        "Stefan Stößlein",
        "Stefan Stößlein",
        "STEFAN STÖSSLEIN",
    ]
    name = pick_case(names)
    assert name is not None
    assert "Stößlein" in name, name

    names = ["Max Strauß", "Max Strauss"]
    name = pick_case(names)
    assert name is not None
    assert "Strauß" in name, name


def test_pick_case_turkish():
    names = ["SEHER DEMİR", "Seher Demi̇r"]
    name = pick_case(names)
    assert name is not None
    assert "Demi̇r" in name, name

    names = ["Süleyman ŞAHİN", "Süleyman Şahi̇n"]
    name = pick_case(names)
    assert name is not None
    assert "Şahi̇n" in name, name


def test_pick_case_armenian():
    names = ["Գեւորգ Սամվելի Գորգիսյան", "Գևորգ Սամվելի Գորգիսյան"]
    name = pick_case(names)
    assert name is not None
    assert "Գևորգ" in name, name


def test_pick_case_greek():
    # ok so:
    # 'ΚΟΣΜΟΣ'.casefold() -> 'κοσμοσ'
    # but:
    # 'Κόσμος'.upper() -> 'ΚΌΣΜΟΣ'
    # that's how you get to 150% debt-to-GDP ratio
    names = ["Κόσμος", "κόσμος", "κόσμος", "ΚΟΣΜΟΣ"]
    name = pick_case(names)
    assert name is not None
    assert "Κόσμος" in name, name


def test_reduce_names():
    names = [
        "Vladimir Vladimirovich Putin",
        "Vladimir Vladimirovich PUTIN",
        "Vladimir Vladimirovich PUTINY",
        "Vladimir Vladimirovich PUTIN",
    ]
    reduced = reduce_names(names)
    assert len(reduced) == 2
    assert "Vladimir Vladimirovich Putin" in reduced
    assert "Vladimir Vladimirovich PUTINY" in reduced

    names = ["Vladimir Putin", "Vladimir PUTIN", "VLADIMIR PUTIN"]
    reduced = reduce_names(names)
    assert len(reduced) == 1
    assert reduced[0] == "Vladimir Putin"

    names = ["."]
    reduced = reduce_names(names)
    assert len(reduced) == 0, reduced

    names = ["Κόσμος", "κόσμος", "κόσμος", "ΚΟΣΜΟΣ"]
    reduced = reduce_names(names)
    assert len(reduced) == 2
    names = ["Κοσμοσ", "κοσμοσ", "κοσμοσ", "ΚΟΣΜΟΣ"]
    reduced = reduce_names(names)
    assert len(reduced) == 1

    reduced = reduce_names([])
    assert len(reduced) == 0, reduced

    names = [".", "6161", " / "]
    reduced = reduce_names(names)
    assert len(reduced) == 0, reduced
