from rigour.addresses import compare_address, compare_address_many


def test_compare_address_identical() -> None:
    assert compare_address("Bahnhofstr. 12, Berlin", "Bahnhofstr. 12, Berlin") == 1.0
    assert compare_address("BAHNHOFSTR 12 BERLIN", "bahnhofstr. 12, berlin") == 1.0


def test_compare_address_order_independent() -> None:
    score = compare_address(
        "Bahnhofstr. 12, 10115 Berlin", "10115 Berlin, Bahnhofstr. 12"
    )
    assert score == 1.0


def test_compare_address_transliteration() -> None:
    score = compare_address("Тверская 4, Москва", "Tverskaya 4, Moskva")
    assert score > 0.8


def test_compare_address_number_conflict() -> None:
    same = compare_address("Hauptstr. 5, 10115 Berlin", "Hauptstr. 5, 10115 Berlin")
    conflict = compare_address(
        "Hauptstr. 5, 10115 Berlin", "Hauptstr. 7, 10115 Berlin"
    )
    assert same == 1.0
    assert conflict < 0.5


def test_compare_address_empty() -> None:
    assert compare_address("", "Bahnhofstr. 12") == 0.0
    assert compare_address("...", "Bahnhofstr. 12") == 0.0
    assert compare_address("", "") == 0.0


def test_compare_address_many_returns_max() -> None:
    queries = ["Calle Mayor 3, Madrid", "Bahnhofstr. 12, Berlin"]
    results = ["10115 Berlin, Bahnhofstrasse 12", "Bahnhofstr. 12, Berlin"]
    assert compare_address_many(queries, results) == 1.0


def test_compare_address_many_empty() -> None:
    assert compare_address_many([], ["Bahnhofstr. 12"]) == 0.0
    assert compare_address_many(["Bahnhofstr. 12"], []) == 0.0
    assert compare_address_many([], []) == 0.0
    assert compare_address_many(["..."], ["Bahnhofstr. 12"]) == 0.0
