from rigour.names.org_types import replace_org_types_display as replace_display
from rigour.names.org_types import replace_org_types_compare as replace_compare
from rigour.names.org_types import extract_org_types, remove_org_types
from rigour.names.org_types import _normalize_compare
# from rigour.names.org_types import normalize_display


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
    assert replace_compare("siemens aktiengesellschaft") == "siemens ag"
    assert replace_compare("siemens ag") == "siemens ag"
    assert replace_compare("siemens ag", generic=True) == "siemens jsc"

    long = "siemens gesellschaft mit beschränkter Haftung"
    assert replace_compare(long) == "siemens gmbh"

    norm = _normalize_compare("FABERLIC EUROPE Sp. z o.o.")
    assert norm is not None
    assert extract_org_types(norm) == [("sp. z o.o.", "spzoo")]
    assert replace_compare(norm) == "faberlic europe spzoo"


def test_extract_org_types():
    assert extract_org_types("siemens aktiengesellschaft") == [
        ("aktiengesellschaft", "ag")
    ]
    assert extract_org_types("siemens g.m.b.h") == [("g.m.b.h", "gmbh")]
    assert extract_org_types("siemens g.m.b.h", generic=True) == [("g.m.b.h", "llc")]
    assert extract_org_types("siemens") == []


def test_remove_org_types():
    assert remove_org_types("siemens aktiengesellschaft").strip() == "siemens"
    assert remove_org_types("siemens g.m.b.h").strip() == "siemens"
    assert remove_org_types("siemens") == "siemens"
    assert remove_org_types("siemens  gmbh").strip() == "siemens"
    assert remove_org_types("siemens aktiengesellschaft gmbh").strip() == "siemens"


def test_cyrillic_prefix():
    # Russian-style placement: org type before the name
    assert replace_compare("ооо газпром") == "ooo газпром"
    assert replace_compare("ооо газпром", generic=True) == "llc газпром"


def test_cyrillic_long_form():
    # Multi-word Cyrillic alias for ООО should be collapsed to compare form
    long = "общество с ограниченной ответственностью газпром"
    assert replace_compare(long) == "ooo газпром"
    assert extract_org_types(long) == [("общество с ограниченной ответственностью", "ooo")]


def test_cjk_word_boundary():
    # 有限公司 = "Limited Company" (alias for Ltd)
    # When embedded in a CJK string with no spaces, the word boundary regex cannot match:
    # 行 is \w under re.U, so (?<!\w) lookbehind fails before 有.
    # This is a known limitation — document expected behavior explicitly.
    norm = _normalize_compare("招商银行有限公司")
    assert norm is not None
    # No match: preceding CJK character is \w, so lookbehind fails
    assert extract_org_types(norm) == []
    # But a space-separated form DOES match:
    assert extract_org_types("招商银行 有限公司") == [("有限公司", "ltd")]


def test_dotted_prefix():
    # Dotted abbreviation placed as a prefix exercises (?<!\w) at start of string
    assert extract_org_types("g.m.b.h siemens") == [("g.m.b.h", "gmbh")]
    assert replace_compare("g.m.b.h siemens") == "gmbh siemens"


def test_no_false_positive_substring():
    # Short org types must not match inside longer words
    # "SA" must not match inside "samsung"
    assert extract_org_types("samsung") == []
    # "AS" must not match inside "astra"
    assert extract_org_types("astra") == []
    # But standalone "samsung sa" should extract SA
    result = extract_org_types("samsung sa")
    assert any(form == "sa" for form, _ in result)


def test_empty_compare_removal():
    # к.д. has compare: "" and generic: LP
    # replace_compare removes it (replaces with empty string)
    assert replace_compare("к.д. company") == " company"
    # generic=True substitutes the generic form instead
    assert replace_compare("к.д. company", generic=True) == "lp company"
    # extract returns the empty string as the compare form
    result = extract_org_types("к.д. company")
    assert result == [("к.д.", "")]


def test_remove_org_types_prefix():
    # Org type as a prefix (not just suffix)
    assert remove_org_types("llc siemens").strip() == "siemens"
    assert remove_org_types("gmbh siemens").strip() == "siemens"
    # Appears both as prefix and suffix
    assert remove_org_types("llc siemens llc").strip() == "siemens"


def test_compound_form():
    # GmbH & Co. KG is a multi-word compound with internal punctuation and spaces.
    # The Replacer matches it as a single unit via the whole-phrase regex.
    norm = _normalize_compare("Siemens GmbH & Co. KG")
    assert norm is not None
    result = extract_org_types(norm)
    forms = [f for f, _ in result]
    assert any("gmbh & co" in f for f in forms)
    # The compare form for GmbH & Co. KG is "gmbhcokg"
    assert any(c == "gmbhcokg" for _, c in result)


def test_no_generic_entry():
    # AB (Swedish Aktiebolag) has no generic field in the YAML.
    # When generic=True is requested, _generic_replacer has no mapping for "ab",
    # so the text is returned unchanged.
    assert replace_compare("siemens ab", generic=True) == "siemens ab"
    assert replace_compare("siemens ab", generic=False) == "siemens ab"
    # Contrast: AG has generic=JSC and IS replaced when generic=True
    assert replace_compare("siemens ag", generic=True) == "siemens jsc"
    assert replace_compare("siemens ag", generic=False) == "siemens ag"


def test_dotted_form_tokenizer_distinction():
    # In the Replacer (org_types.py), dots are preserved by _normalize_compare.
    # "sp. z o.o." is matched as-is and maps to compare form "spzoo".
    norm = _normalize_compare("Sp. z o.o.")
    assert norm is not None
    assert extract_org_types(norm) == [("sp. z o.o.", "spzoo")]
    # replace_compare also works with the dotted form
    norm2 = _normalize_compare("FABERLIC EUROPE Sp. z o.o.")
    assert norm2 is not None
    assert replace_compare(norm2) == "faberlic europe spzoo"
