from normality import squash_spaces
from rigour.addresses import (
    normalize_address,
    remove_address_keywords,
    shorten_address_keywords,
)


def test_normalize_address():
    address = "Bahnhofstr. 10, 86150 Augsburg, Germany"
    assert normalize_address(address) == "bahnhofstr 10 86150 augsburg germany"

    address = "160 Broad St, Birmingham B15 1DT"
    assert normalize_address(address) == "160 broad st birmingham b15 1dt"

    address = "160 Broad` St, Birmingham B15 1DT"
    assert normalize_address(address) == "160 broad st birmingham b15 1dt"

    address = "160 Broad Street, Birmingham B15 1DT"
    normalized = normalize_address(address)
    assert normalized is not None
    assert shorten_address_keywords(normalized) == "160 broad st birmingham b15 1dt"
    removed = remove_address_keywords(normalized)
    assert removed is not None
    removed = squash_spaces(removed)
    assert removed == "160 broad birmingham b15 1dt"

    address = "Marlborough House, Pall Mall, London SW1Y 5HX"
    normalized = normalize_address(address)
    assert normalized == "marlborough house pall mall london sw1y 5hx"
    removed = remove_address_keywords(normalized)
    assert removed is not None
    removed = squash_spaces(removed)
    assert removed == "marlborough pall mall london sw1y 5hx"

    assert normalize_address("hey") is None
    assert normalize_address("") is None
    assert normalize_address("h e") is None

    assert (
        normalize_address("Д.127, АМУРСКАЯ, АМУРСКАЯ, 675000")
        == "д 127 амурская амурская 675000"
    )
    assert (
        normalize_address("Д.127, АМУРСКАЯ, АМУРСКАЯ, 675000", latinize=True)
        == "d 127 amurskaa amurskaa 675000"
    )


def test_shorten_address_keywords():
    cases = [
        ("New York Street, New York, NY 10001", "ny st ny 10001"),
        ("Islamic Republic of Iran", "ir"),
        ("Iran", "ir"),
        ("United Arab Emirates", "ae"),
    ]
    for address, expected in cases:
        normalized = normalize_address(address)
        assert normalized is not None
        shortened = shorten_address_keywords(normalized)
        assert shortened == expected


# --- Boundary semantics of the address replacer ---
#
# The replacer matches forms with `(?<!\w)X(?!\w)` lookarounds.
# These tests pin the contract so any reimplementation of the
# replacer must reproduce the same boundary behaviour.


def test_replacer_match_at_string_start():
    # BOS satisfies (?<!\w) — form at the start of string matches.
    normalized = normalize_address("Iran capital")
    assert normalized is not None
    assert shorten_address_keywords(normalized) == "ir capital"


def test_replacer_match_at_string_end():
    # EOS satisfies (?!\w) — form at the end of string matches.
    normalized = normalize_address("capital of Iran")
    assert normalized is not None
    assert shorten_address_keywords(normalized) == "capital of ir"


def test_replacer_match_surrounded_by_whitespace():
    # Form surrounded by whitespace on both sides matches. Use
    # nonsense surrounding tokens so we don't accidentally hit
    # other entries in the mapping.
    normalized = normalize_address("zzz Iran qqq")
    assert normalized is not None
    assert shorten_address_keywords(normalized) == "zzz ir qqq"


def test_replacer_no_match_when_form_is_suffix_of_word():
    # "iran" is a substring of "iranian" — preceded by nothing but
    # followed by `i` which is \w — must not match.
    normalized = normalize_address("Iranian capital")
    assert normalized is not None
    assert "iranian" in normalized
    assert shorten_address_keywords(normalized) == "iranian capital"


def test_replacer_no_match_when_form_is_prefix_of_word():
    # "iran" preceded by `k` (\w) inside "kiran" — must not match.
    normalized = normalize_address("Kiran lake")
    assert normalized is not None
    assert shorten_address_keywords(normalized) == "kiran lake"


def test_replacer_no_match_when_form_is_infix_of_word():
    # "iran" inside "biranian" — flanked on both sides by \w.
    normalized = normalize_address("biranian street")
    assert normalized is not None
    # "street" still matches; "iran" inside "biranian" must not.
    assert shorten_address_keywords(normalized) == "biranian st"


def test_replacer_multiple_non_overlapping_matches():
    # Two occurrences of the same form in one string both get
    # substituted independently. Using one well-known form
    # (`"street" → "st"`) twice avoids unrelated mappings biting
    # surrounding tokens.
    normalized = normalize_address("zzz street qqq street")
    assert normalized is not None
    shortened = shorten_address_keywords(normalized)
    assert shortened == "zzz st qqq st"


def test_replacer_longest_form_preferred():
    # "united arab emirates" is mapped to "ae". A naive alternation
    # could match the shorter form for "united" or "arab" first; the
    # longest-form ordering ensures the multi-token form wins.
    normalized = normalize_address("United Arab Emirates")
    assert normalized is not None
    assert shorten_address_keywords(normalized) == "ae"


def test_replacer_unicode_word_boundary():
    # \w under re.U matches Cyrillic letters. A form preceded by a
    # Cyrillic word character must not match. Construct a synthetic
    # case: "ст iran" where "ст" is Cyrillic and is followed by a
    # space, so "iran" still matches (boundary holds via the space).
    # But "стiran" run together must not match "iran".
    normalized = normalize_address("стiran capital")
    assert normalized is not None
    # "iran" is preceded by Cyrillic т (a word char in re.U mode), so
    # the boundary check fails and no substitution happens.
    shortened = shorten_address_keywords(normalized)
    assert shortened is not None
    assert "стiran" in shortened
    assert "ir" not in shortened.split()


def test_remove_address_keywords_substitutes_with_whitespace():
    # remove_address_keywords drops matched forms, replacing each
    # with a single whitespace by default.
    normalized = normalize_address("160 Broad Street Birmingham")
    assert normalized is not None
    removed = remove_address_keywords(normalized)
    assert removed is not None
    # "street" gets removed; "broad" and "birmingham" survive.
    assert "street" not in removed.split()
    assert "broad" in removed
    assert "birmingham" in removed


def test_remove_address_keywords_does_not_collapse_whitespace():
    # Docstring contract: consecutive matches produce consecutive
    # whitespace; we don't squash it.
    normalized = normalize_address("street avenue road")
    assert normalized is not None
    removed = remove_address_keywords(normalized)
    assert removed is not None
    # Three consecutive matched forms → multiple whitespace runs.
    # Non-collapsed whitespace will produce >1 consecutive space.
    assert "  " in removed
