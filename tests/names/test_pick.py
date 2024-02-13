from rigour.names.pick import pick_name, levenshtein_pick

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


def test_pick_nothing():
    name = pick_name([])
    assert name is None
    name = pick_name([""])
    assert name is None


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