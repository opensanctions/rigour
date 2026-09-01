from rigour.addresses import (
    address_fingerprint,
    compare_address,
    compare_address_many,
)


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


def test_address_fingerprint_canonical_forms() -> None:
    key = address_fingerprint("Main Boulevard 5, Syrian Arab Republic")
    assert key == "main blvd 5 sy"
    assert address_fingerprint("Main Blvd. 5, Syria") == key


def test_address_fingerprint_transliterates() -> None:
    key = address_fingerprint("Воткинское шоссе, д. 170")
    assert key == "votkinskoe hwy d 170"


def test_address_fingerprint_order_preserved() -> None:
    one = address_fingerprint("Д. 17 СТР. 1, Москва")
    other = address_fingerprint("Д. 1 СТР. 17, Москва")
    assert one is not None
    assert one != other


def test_address_fingerprint_native_script_passthrough() -> None:
    key = address_fingerprint("北京市 100022")
    assert key == "北京市 100022"


def test_address_fingerprint_empty() -> None:
    assert address_fingerprint("") is None
    assert address_fingerprint(" ,,, --- ") is None
