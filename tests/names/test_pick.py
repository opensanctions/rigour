import pytest
from rigour.names.pick import pick_name

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


@pytest.mark.skip
def test_pick_titlecase():
    names = [
        "Vladimir Vladimirovich Putin",
        "Vladimir Vladimirovich PUTIN",
        "Vladimir Vladimirovich PUTIN",
    ]
    name = pick_name(names)
    assert name is not None
    assert "Putin" in name, names
