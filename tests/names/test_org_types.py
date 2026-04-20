from rigour.names.org_types import (
    extract_org_types,
    remove_org_types,
    replace_org_types_compare as replace_compare,
    replace_org_types_display as replace_display,
)
from rigour.text.normalize import Cleanup, Normalize, normalize

# Flag composition matching the old Python default `_normalize_compare`
# (squash + casefold). Tests that pre-normalise text before calling the
# extract/compare/remove variants use this so their outputs stay
# comparable to the pre-flags-era expectations.
_COMPARE_FLAGS = Normalize.CASEFOLD | Normalize.SQUASH_SPACES


def _compare_norm(text: str) -> str:
    """Normalise input with the same flags the compare replacer uses —
    tests assume the caller pre-normalises, same contract as nomenklatura
    and yente."""
    out = normalize(text, _COMPARE_FLAGS, Cleanup.Noop)
    assert out is not None
    return out


def test_display_form():
    assert replace_display("Siemens Aktiengesellschaft") == "Siemens AG"
    assert replace_display("Siemens AG") == "Siemens AG"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long) == "Siemens GmbH"

    long = "Siemens gesellschaft mit beschränkter Haftung"
    assert replace_display(long.upper()) == "Siemens GmbH".upper()

    assert replace_display("Banana") == "Banana"
    assert replace_display("GmbH") == "GmbH"
    assert replace_display("GMBH") == "GMBH"


def test_compare_form():
    assert replace_compare("siemens aktiengesellschaft", _COMPARE_FLAGS) == "siemens ag"
    assert replace_compare("siemens ag", _COMPARE_FLAGS) == "siemens ag"
    assert replace_compare("siemens ag", _COMPARE_FLAGS, generic=True) == "siemens jsc"

    long = "siemens gesellschaft mit beschränkter haftung"
    assert replace_compare(long, _COMPARE_FLAGS) == "siemens gmbh"

    norm = _compare_norm("FABERLIC EUROPE Sp. z o.o.")
    assert extract_org_types(norm, _COMPARE_FLAGS) == [("sp. z o.o.", "spzoo")]
    assert replace_compare(norm, _COMPARE_FLAGS) == "faberlic europe spzoo"


def test_extract_org_types():
    assert extract_org_types("siemens aktiengesellschaft", _COMPARE_FLAGS) == [
        ("aktiengesellschaft", "ag")
    ]
    assert extract_org_types("siemens g.m.b.h", _COMPARE_FLAGS) == [("g.m.b.h", "gmbh")]
    assert extract_org_types("siemens g.m.b.h", _COMPARE_FLAGS, generic=True) == [
        ("g.m.b.h", "llc")
    ]
    assert extract_org_types("siemens", _COMPARE_FLAGS) == []


def test_remove_org_types():
    assert remove_org_types("siemens aktiengesellschaft", normalize_flags=_COMPARE_FLAGS).strip() == "siemens"
    assert remove_org_types("siemens g.m.b.h", normalize_flags=_COMPARE_FLAGS).strip() == "siemens"
    assert remove_org_types("siemens", normalize_flags=_COMPARE_FLAGS) == "siemens"
    assert remove_org_types("siemens  gmbh", normalize_flags=_COMPARE_FLAGS).strip() == "siemens"
    assert (
        remove_org_types("siemens aktiengesellschaft gmbh", normalize_flags=_COMPARE_FLAGS).strip()
        == "siemens"
    )


def test_cyrillic_prefix():
    # Russian-style placement: org type before the name
    assert replace_compare("ооо газпром", _COMPARE_FLAGS) == "ooo газпром"
    assert replace_compare("ооо газпром", _COMPARE_FLAGS, generic=True) == "llc газпром"


def test_cyrillic_long_form():
    # Multi-word Cyrillic alias for ООО should be collapsed to compare form
    long = "общество с ограниченной ответственностью газпром"
    assert replace_compare(long, _COMPARE_FLAGS) == "ooo газпром"
    assert extract_org_types(long, _COMPARE_FLAGS) == [
        ("общество с ограниченной ответственностью", "ooo")
    ]


def test_cjk_word_boundary():
    # 有限公司 = "Limited Company" (alias for Ltd). When embedded in a
    # CJK string with no spaces, the word boundary predicate cannot
    # match: 行 is a word char, so the (?<!\w) equivalent fails before
    # 有. Documented limitation — same behaviour as the Python impl.
    norm = _compare_norm("招商银行有限公司")
    assert extract_org_types(norm, _COMPARE_FLAGS) == []
    # But a space-separated form DOES match:
    assert extract_org_types("招商银行 有限公司", _COMPARE_FLAGS) == [("有限公司", "ltd")]


def test_dotted_prefix():
    # Dotted abbreviation placed as a prefix exercises the leading
    # boundary check at start-of-string.
    assert extract_org_types("g.m.b.h siemens", _COMPARE_FLAGS) == [("g.m.b.h", "gmbh")]
    assert replace_compare("g.m.b.h siemens", _COMPARE_FLAGS) == "gmbh siemens"


def test_no_false_positive_substring():
    # Short org types must not match inside longer words.
    assert extract_org_types("samsung", _COMPARE_FLAGS) == []
    assert extract_org_types("astra", _COMPARE_FLAGS) == []
    # Standalone "samsung sa" should extract SA
    result = extract_org_types("samsung sa", _COMPARE_FLAGS)
    assert any(form == "sa" for form, _ in result)


def test_empty_compare_removal():
    # к.д. has compare: "" and generic: LP
    assert replace_compare("к.д. company", _COMPARE_FLAGS) == " company"
    # generic=True substitutes the generic form instead
    assert replace_compare("к.д. company", _COMPARE_FLAGS, generic=True) == "lp company"
    # extract returns the empty string as the compare form
    result = extract_org_types("к.д. company", _COMPARE_FLAGS)
    assert result == [("к.д.", "")]


def test_remove_org_types_prefix():
    assert remove_org_types("llc siemens", normalize_flags=_COMPARE_FLAGS).strip() == "siemens"
    assert remove_org_types("gmbh siemens", normalize_flags=_COMPARE_FLAGS).strip() == "siemens"
    # Appears both as prefix and suffix
    assert remove_org_types("llc siemens llc", normalize_flags=_COMPARE_FLAGS).strip() == "siemens"


def test_compound_form():
    # GmbH & Co. KG is a multi-word compound with internal punctuation
    # and spaces. The Replacer matches it as a single unit.
    norm = _compare_norm("Siemens GmbH & Co. KG")
    result = extract_org_types(norm, _COMPARE_FLAGS)
    forms = [f for f, _ in result]
    assert any("gmbh & co" in f for f in forms)
    # The compare form for GmbH & Co. KG is "gmbhcokg"
    assert any(c == "gmbhcokg" for _, c in result)


def test_no_generic_entry():
    # AB (Swedish Aktiebolag) has no generic field in the YAML. When
    # generic=True is requested, the generic replacer has no mapping
    # for "ab", so the text is returned unchanged.
    assert replace_compare("siemens ab", _COMPARE_FLAGS, generic=True) == "siemens ab"
    assert replace_compare("siemens ab", _COMPARE_FLAGS, generic=False) == "siemens ab"
    # Contrast: AG has generic=JSC and IS replaced when generic=True
    assert replace_compare("siemens ag", _COMPARE_FLAGS, generic=True) == "siemens jsc"
    assert replace_compare("siemens ag", _COMPARE_FLAGS, generic=False) == "siemens ag"


def test_dotted_form_tokenizer_distinction():
    # Dots are preserved by the compare normalisation; "sp. z o.o."
    # is matched as-is and maps to compare form "spzoo".
    norm = _compare_norm("Sp. z o.o.")
    assert extract_org_types(norm, _COMPARE_FLAGS) == [("sp. z o.o.", "spzoo")]
    norm2 = _compare_norm("FABERLIC EUROPE Sp. z o.o.")
    assert replace_compare(norm2, _COMPARE_FLAGS) == "faberlic europe spzoo"


def test_production_default_flags_are_casefold_only():
    # nomenklatura/yente/FTM pre-normalise names with prenormalize_name
    # (casefold only) and call replace_org_types_compare without flags.
    # That path must work out of the box with the new default.
    casefolded = "siemens aktiengesellschaft"
    assert replace_compare(casefolded) == "siemens ag"
