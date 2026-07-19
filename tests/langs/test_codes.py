from rigour.data.langs.iso639 import ISO3_ALL
from rigour.langs import iso_639_alpha3, iso_639_alpha2
from rigour.langs import list_to_alpha3, is_lang_better
from rigour.langs import PREFERRED_LANG, PREFERRED_LANGS


def test_preferred():
    assert iso_639_alpha3(PREFERRED_LANG) == PREFERRED_LANG
    for lang in PREFERRED_LANGS:
        assert iso_639_alpha3(lang) == lang
        assert iso_639_alpha2(lang) is not None


def test_alpha3():
    assert iso_639_alpha3("") is None
    assert iso_639_alpha3("banana") is None
    assert iso_639_alpha3("gub") == "gub"
    assert iso_639_alpha3("en") == "eng"
    assert iso_639_alpha3("eng") == "eng"
    assert iso_639_alpha3("de") == "deu"
    assert iso_639_alpha3("ger") == "deu"
    assert iso_639_alpha3("yu") is None
    assert iso_639_alpha3("mul") is None
    assert iso_639_alpha3("mul") is None


def test_alpha3_subtags():
    # IETF/BCP 47-style tags resolve via their primary subtag:
    assert iso_639_alpha3("zh-Hans") == "zho"
    assert iso_639_alpha3("zh-hant") == "zho"
    assert iso_639_alpha3("pt-BR") == "por"
    assert iso_639_alpha3("en-gb") == "eng"
    assert iso_639_alpha3("sr-el") == "srp"
    assert iso_639_alpha3("be-tarask") == "bel"
    assert iso_639_alpha3("kk-cyrl") == "kaz"
    assert iso_639_alpha3("crh-latn") == "crh"
    # A known full tag wins over subtag splitting (synonym table):
    assert iso_639_alpha3("chi_sim") == "zho"
    assert iso_639_alpha3("aze_cyrl") == "aze"
    # Collective and non-language primary subtags still fail:
    assert iso_639_alpha3("roa-tara") is None
    assert iso_639_alpha3("mul-x-foo") is None
    assert iso_639_alpha2("pt-BR") == "pt"


def test_alpha2():
    assert iso_639_alpha2("") is None
    assert iso_639_alpha2("banana") is None
    assert iso_639_alpha2("gub") is None
    assert iso_639_alpha2("eng") == "en"


def test_list():
    assert "srp" in list_to_alpha3(["bs"])
    assert "srp" not in list_to_alpha3(["bs"], synonyms=False)
    assert "deu" in list_to_alpha3(["bs", "de"])
    assert "eng" in list_to_alpha3(["en"])
    assert not len(list_to_alpha3(["xy"]))
    assert not len(list_to_alpha3([""]))


def test_list_only_valid_codes():
    # Synonym expansion must not leak non-ISO-639-3 codes (639-2/B or
    # Tesseract-style, e.g. "ger", "chi") into the output set.
    for inputs in (["de"], ["zho"], ["sqi"], ["srp"], ["mya"]):
        assert list_to_alpha3(inputs) <= ISO3_ALL, inputs


def test_old_norse_not_norwegian():
    # "non" (Old Norse) is a distinct language, not a code-variant of
    # Norwegian ("nor"); the two must not resolve to or expand into each other.
    assert iso_639_alpha3("non") == "non"
    assert iso_639_alpha3("nor") == "nor"
    assert "non" not in list_to_alpha3(["nor"])
    assert "nor" not in list_to_alpha3(["non"])


def test_albanian_synonyms():
    # Albanian is "sqi"; the 639-2/B code "alb" resolves to it and the two
    # are synonyms. "sli" (Lower Silesian) is unrelated and must stay separate.
    assert iso_639_alpha3("alb") == "sqi"
    assert "sqi" in list_to_alpha3(["alb"])
    assert iso_639_alpha3("sli") == "sli"
    assert "sqi" not in list_to_alpha3(["sli"])


def test_burmish_languages_distinct():
    # Burmese "mya"/"bur" are synonyms, but the related Burmish languages
    # (Intha "int", Rakhine "rki", ...) are distinct and expand to themselves.
    assert list_to_alpha3(["mya"]) == {"mya"}
    assert list_to_alpha3(["int"]) == {"int"}
    assert list_to_alpha3(["rki"]) == {"rki"}


def test_nepali_collapses_to_macrolanguage():
    # The individual language "npi" is collapsed into the macrolanguage "nep"
    # (which carries the two-letter code "ne"), so Nepali resolves to one code.
    assert iso_639_alpha3("npi") == "nep"
    assert iso_639_alpha3("ne") == "nep"
    assert iso_639_alpha3("Nepali") == "nep"
    assert iso_639_alpha2("nep") == "ne"


def test_no_linguistic_content():
    # "zxx" ("no linguistic content") is treated as a non-language.
    assert iso_639_alpha3("zxx") is None


def test_is_better():
    assert is_lang_better("eng", "deu")
    assert not is_lang_better("eng", "eng")
    assert not is_lang_better("fra", "eng")
    assert is_lang_better("eng", "xyz")
    assert not is_lang_better("xyz", "eng")
    assert not is_lang_better("xyz", "abc")
