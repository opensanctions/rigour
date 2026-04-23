import pytest
from rigour.langs import LangStr, PREFERRED_LANG
from rigour.names.pick import (
    pick_name,
    pick_lang_name,
    pick_case,
    reduce_names,
    representative_names,
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


def test_pick_lang_name():
    assert pick_lang_name([]) is None
    assert pick_lang_name(TAGGED) == "Mitch McConnell"

    other_langs = [
        LangStr("Митч Макконнелл", lang="rus"),
        LangStr("میتچ ماکونل", lang="ara"),
        LangStr("ミッチ・マコーネル", lang="jpn"),
        LangStr("ミッチ・マコーネル", lang="jpn"),
        LangStr("ミッチ・マコーネル", lang="jpn"),
        LangStr("ミッチ・マコーネル", lang="jpn"),
        LangStr("米奇·麥康諾", lang="zho"),
        LangStr("미치 매코널", lang="kor"),
    ]
    assert pick_lang_name(other_langs) == "Митч Макконнелл"

    other_langs = [LangStr(" ", lang="rus")]
    assert pick_lang_name(other_langs) is None

    no_langs = [
        LangStr("Mitch McConne", lang=None),
        LangStr("Mitch McConne", lang=None),
        LangStr("Mitch McConne", lang=None),
    ]
    assert pick_lang_name(no_langs) == "Mitch McConne"

    no_langs = [LangStr(" ", lang=None)]
    assert pick_lang_name(no_langs) is None


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

    cases = [
        "Vladimir PuTin",
        "VlaDimir PuTin",
        "Vladimir PUTIN",
        "VLADIMIR PUTIN",
    ]
    assert pick_case(cases) == "Vladimir PuTin"

    cases = [
        "Vladimir PuTin",
        "VlaDimir PuTin",
        "vladimir PUTINO",
        "VLADIMIR pUTIN",
    ]
    assert pick_case(cases) == "Vladimir PuTin"


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

    # None of the names are lowercase, which makes them all different from the base:
    names = ["Ahmet ÇİÇEK", "AHMET ÇİÇEK"]
    name = pick_case(names)
    assert name is not None
    assert "Ahmet" in name, name


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


def test_pick_ordering():
    names = [
        "OCEAN SHIP MANAGEMENT AND OPERATION LLC",
        "OCEAN SHIP MANAGEMENT and OPERATION LLC",
    ]
    onames = [
        "OCEAN SHIP MANAGEMENT and OPERATION LLC",
        "OCEAN SHIP MANAGEMENT AND OPERATION LLC",
    ]
    assert pick_name(names) == pick_name(onames)


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
    assert len(reduced) == 1, reduced

    names = ["764"]
    reduced = reduce_names(names)
    assert len(reduced) == 1, reduced

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
    assert len(reduced) == 3, reduced


# ---- representative_names ----


def test_representative_names_empty_and_limits():
    assert representative_names([], 5) == []
    assert representative_names(["Vladimir Putin"], 0) == []
    assert representative_names(["Vladimir Putin"], -1) == []


def test_representative_names_passthrough_short():
    # Fewer inputs than limit → returns them (after reduce_names dedup).
    names = ["Vladimir Putin", "Vladimir PUTIN"]
    reps = representative_names(names, 5)
    assert reps == ["Vladimir Putin"]


def test_representative_names_transliterations_collapse():
    # 20 transliterations of one Cyrillic name should collapse to a
    # handful of reps — enough to cover distinct Romanization schemes
    # and the Cyrillic original, not 20 near-identical Latin queries.
    ermakov = [
        "ERMAKOV Valery Nikolaevich",
        "Ermacov Valeryi Nycolaevych",
        "Ermakov Valerij Nikolaevich",
        "Ermakov Valerij Nikolaevič",
        "Ermakov Valerijj Nikolaevich",
        "Ermakov Valeriy Nikolaevich",
        "Ermakov Valery Nykolaevych",
        "Ermakov Valeryi Nykolaevych",
        "Ermakov Valeryy Nikolaevich",
        "Ermakov Valeryy Nykolaevych",
        "Ermakov Valerȳĭ Nȳkolaevȳch",
        "Iermakov Valerii Mykolaiovych",
        "Jermakov Valerij Mikolajovich",
        "Jermakov Valerij Mikolajovič",
        "Jermakov Valerij Mykolajovyč",
        "Yermakov Valerii Mykolaiovych",
        "Yermakov Valerij Mykolajovych",
        "Yermakov Valeriy Mykolayovych",
        "Êrmakov Valerìj Mikolajovič",
        "ЕРМАКОВ Валерий Николаевич",
    ]
    reps = representative_names(ermakov, 10)
    # Much fewer than the 20 inputs — the cap is enforced.
    assert 1 <= len(reps) <= 5, reps
    # The Cyrillic original is its own cluster (distance ~1.0 to every
    # Latin form) and should be represented.
    assert any(any("Ѐ" <= c <= "ӿ" for c in r) for r in reps), reps


def test_representative_names_distinct_names_mandela():
    # Nelson Mandela was also known as Rolihlahla Mandela — genuinely
    # different names. Both should be represented.
    aliases = ["Nelson Mandela", "Rolihlahla Mandela"]
    reps = representative_names(aliases, 5)
    assert len(reps) == 2, reps
    joined = " ".join(reps).lower()
    assert "nelson" in joined
    assert "rolihlahla" in joined


def test_representative_names_limit_is_a_cap():
    # Even with limit=10, one-cluster input (case-variants of a single
    # name) returns 1. The cap is an upper bound, not a quota.
    aliases = ["Vladimir Putin", "VLADIMIR PUTIN", "vladimir putin"]
    reps = representative_names(aliases, 10)
    assert reps == ["Vladimir Putin"]


def test_representative_names_returns_originals():
    # Output strings are originals from the input (not casefolded /
    # normalised). pick_name picks the best-case variant per cluster.
    aliases = ["VLADIMIR PUTIN", "Vladimir Putin", "vladimir putin"]
    reps = representative_names(aliases, 3)
    assert reps == ["Vladimir Putin"]


def test_representative_names_threshold_tunable():
    # "John Smith" vs "John Smithey" — lev=3, max_len=12, ratio=0.25.
    # Tight threshold splits them, loose threshold merges.
    aliases = ["John Smith", "John Smithey"]
    tight = representative_names(aliases, 5, cluster_threshold=0.1)
    loose = representative_names(aliases, 5, cluster_threshold=0.5)
    assert len(tight) == 2, tight
    assert len(loose) == 1, loose
