from rigour.addresses import (
    AddressMatch,
    address_fingerprint,
    compare_address,
    compare_address_many,
    match_addresses,
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


def test_match_addresses_returns_winning_pair() -> None:
    queries = ["Calle Mayor 3, Madrid", "Bahnhofstr. 12, Berlin"]
    results = ["10115 Berlin, Bahnhofstrasse 12", "Bahnhofstr. 12, Berlin"]
    match = match_addresses(queries, results)
    assert match is not None
    assert isinstance(match, AddressMatch)
    assert match.score == 1.0
    assert match.query == "Bahnhofstr. 12, Berlin"
    assert match.result == "Bahnhofstr. 12, Berlin"
    assert match.detail == "bahnhofstr 12 berlin"
    assert match.score == compare_address_many(queries, results)
    assert repr(match).startswith("AddressMatch(score=1.000, ")


def test_match_addresses_detail_grammar() -> None:
    match = match_addresses(["Sunset Boulevard 12, Los Angeles"], ["Sunset Blvd 12, LA"])
    assert match is not None
    assert match.detail == "sunset boulevard~blvd 12 -los -angeles +la"
    match = match_addresses(["Bahnhofstrasse 12, Berlin"], ["Bahnhofstrase 12, Berlin"])
    assert match is not None
    assert match.detail == "bahnhofstrasse~bahnhofstrase 12 berlin"
    match = match_addresses(["Hauptstr. 5, 10115 Berlin"], ["Hauptstr. 7, 10115 Berlin"])
    assert match is not None
    assert match.detail == "hauptstr 10115 berlin -5 +7"


def test_match_addresses_none_and_zero() -> None:
    assert match_addresses([], ["Bahnhofstr. 12"]) is None
    assert match_addresses(["Bahnhofstr. 12"], []) is None
    assert match_addresses(["..."], ["Bahnhofstr. 12"]) is None
    match = match_addresses(["Bahnhofstr. 12, Berlin"], ["Calle Mayor 3, Madrid"])
    assert match is not None
    assert match.score < 0.2
    assert match.detail.startswith("-")
