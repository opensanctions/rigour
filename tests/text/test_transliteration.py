"""Test transliteration (ascii_text, latinize_text) across all target languages.

Exercises rigour.text.transliteration (Rust/ICU4X). Expected values were
originally generated against PyICU/normality; where ICU4X diverges the
pins have been updated with a note explaining the change.
"""

from rigour.text.transliteration import ascii_text, latinize_text


# --- Fast-path and trivial inputs ---


def test_ascii_passthrough() -> None:
    """Pure ASCII input returned unchanged."""
    assert ascii_text("John Spencer") == "John Spencer"
    assert ascii_text("hello123") == "hello123"
    assert ascii_text("C.I.A.") == "C.I.A."


def test_ascii_empty() -> None:
    assert ascii_text("") == ""


# --- Latin-script languages (diacritics to ASCII) ---


def test_ascii_german() -> None:
    """German: umlauts, eszett."""
    assert ascii_text("Hans-Peter Müller") == "Hans-Peter Muller"
    assert ascii_text("Stefan Stößlein") == "Stefan Stosslein"


def test_ascii_french() -> None:
    """French: cedilla, accents."""
    assert ascii_text("François Hollande") == "Francois Hollande"
    assert ascii_text("Jean-Claude Juncker") == "Jean-Claude Juncker"


def test_ascii_spanish() -> None:
    """Spanish: double surname, accent on í/ó."""
    assert ascii_text("María García López") == "Maria Garcia Lopez"
    assert ascii_text("José Luis Rodríguez Zapatero") == "Jose Luis Rodriguez Zapatero"


def test_ascii_portuguese() -> None:
    """Portuguese: particle 'da', accent on á."""
    assert ascii_text("Luiz Inácio Lula da Silva") == "Luiz Inacio Lula da Silva"
    assert ascii_text("António Guterres") == "Antonio Guterres"


def test_ascii_swedish() -> None:
    """Swedish: ö."""
    assert ascii_text("Göran Persson") == "Goran Persson"
    assert ascii_text("Fredrik Reinfeldt") == "Fredrik Reinfeldt"


def test_ascii_norwegian_danish() -> None:
    """Norwegian/Danish: ø, hyphenated surname.

    Conscious divergence from PyICU: PyICU produced "Lars Lo/kke Rasmussen"
    with a stray "/" after the handled ø. ICU4X + our fallback table maps
    ø → o cleanly, which is the correct ASCII form.
    """
    assert ascii_text("Lars Løkke Rasmussen") == "Lars Lokke Rasmussen"
    assert ascii_text("Helle Thorning-Schmidt") == "Helle Thorning-Schmidt"


def test_ascii_finnish() -> None:
    """Finnish: ö, double vowels preserved."""
    assert ascii_text("Sauli Niinistö") == "Sauli Niinisto"


def test_ascii_lithuanian() -> None:
    """Lithuanian: ė, specific Baltic diacritics."""
    assert ascii_text("Dalia Grybauskeitė") == "Dalia Grybauskeite"
    assert ascii_text("Gitanas Nausėda") == "Gitanas Nauseda"


def test_ascii_estonian() -> None:
    """Estonian: basic Latin in these names."""
    assert ascii_text("Kersti Kaljulaid") == "Kersti Kaljulaid"


def test_ascii_hungarian() -> None:
    """Hungarian: surname-first order, various accented vowels."""
    assert ascii_text("Orbán Viktor") == "Orban Viktor"
    assert ascii_text("Szijjártó Péter") == "Szijjarto Peter"


def test_ascii_dutch() -> None:
    """Dutch: particle 'van der'."""
    assert ascii_text("Jan Peter van der Berg") == "Jan Peter van der Berg"
    assert ascii_text("Mark Rutte") == "Mark Rutte"


def test_ascii_polish() -> None:
    """Polish: ł, ą, ę, ó, ś, ć, ń."""
    assert ascii_text("Andrzej Duda") == "Andrzej Duda"
    assert ascii_text("Małgorzata Gersdorf") == "Malgorzata Gersdorf"


def test_ascii_turkish() -> None:
    """Turkish: ğ, ş, ö, ü."""
    assert ascii_text("Recep Tayyip Erdoğan") == "Recep Tayyip Erdogan"
    assert ascii_text("Süleyman Şahin") == "Suleyman Sahin"


def test_ascii_azeri() -> None:
    """Azerbaijani: ə, ğ, ö, ü — common in AML/KYC data."""
    assert ascii_text("əhməd") == "ahmad"
    assert ascii_text("FUAD ALIYEV ƏHMƏD OĞLU") == "FUAD ALIYEV AHMAD OGLU"


# --- Cyrillic script ---


def test_ascii_ukrainian_poroshenko() -> None:
    """Ukrainian: end-to-end check from normality test suite."""
    assert ascii_text("Порошенко Петро Олексійович") == "Porosenko Petro Oleksijovic"


def test_ascii_russian() -> None:
    """Russian Cyrillic to Latin transliteration."""
    assert (
        ascii_text("Владимир Владимирович Путин")
        == "Vladimir Vladimirovic Putin"
    )
    assert (
        ascii_text("Ротенберг Аркадий Романович")
        == "Rotenberg Arkadij Romanovic"
    )


def test_ascii_ukrainian() -> None:
    """Ukrainian Cyrillic (has specific letters distinct from Russian)."""
    assert (
        ascii_text("Тимошенко Юлія Володимирівна")
        == "Timosenko Ulia Volodimirivna"
    )


# --- Greek ---


def test_ascii_greek() -> None:
    """Modern Greek to Latin transliteration."""
    assert ascii_text("Κυριάκος Μητσοτάκης") == "Kyriakos Metsotakes"
    assert ascii_text("Νίκος Καζαντζάκης") == "Nikos Kazantzakes"


# --- Armenian ---


def test_ascii_armenian() -> None:
    """Armenian script to Latin transliteration."""
    assert ascii_text("Միթչել Մակքոնել") == "Mit'c'el Makk'onel"
    assert ascii_text("Գեւորգ Սամվելի Գորգիսյան") == "Geworg Samveli Gorgisyan"


# --- Georgian ---


def test_ascii_georgian() -> None:
    """Georgian Mkhedruli script to Latin transliteration."""
    assert ascii_text("ნინო ბურჯანაძე") == "nino burjanadze"
    assert ascii_text("მიხეილ სააკაშვილი") == "mikheil saak'ashvili"


# --- Arabic ---


def test_ascii_arabic() -> None:
    """Arabic script to Latin transliteration (partial — known limitation).

    Conscious divergence from PyICU on the second input: PyICU emitted a "?"
    where ICU4X produces the ayn marker (ʿ), which our ASCII fallback maps
    to an apostrophe. The ICU4X output is strictly more informative.
    """
    assert ascii_text("بشار الأسد") == "bshar alasd"
    assert ascii_text("محمد بن سلمان آل سعود") == "mhmd bn slman al s'wd"


# --- East Asian ---


def test_ascii_chinese() -> None:
    """Simplified Chinese to Pinyin ASCII."""
    assert ascii_text("习近平") == "xi jin ping"
    assert ascii_text("招商银行有限公司") == "zhao shang yin xing you xian gong si"


def test_ascii_japanese() -> None:
    """Japanese Kanji and Katakana to Latin.

    Conscious divergence from PyICU on the Katakana input: PyICU emitted a
    "?" for the Japanese middle dot (・, U+30FB) between words. ICU4X passes
    it through and our ASCII fallback maps it to a space — matching the
    dot's role as a Japanese word separator.
    """
    assert ascii_text("高市早苗") == "gao shi zao miao"
    assert ascii_text("ウラジーミル・プーチン") == "urajimiru puchin"


def test_ascii_korean() -> None:
    """Korean Hangul to Latin."""
    assert ascii_text("김민석") == "gimminseog"
    assert ascii_text("박근혜") == "baggeunhye"


# --- Mixed script ---


def test_ascii_mixed_script() -> None:
    """Mixed scripts in one string."""
    assert ascii_text("Tokyo東京") == "Tokyo dong jing"
    assert ascii_text("Café René") == "Cafe Rene"


# --- Organization names ---


def test_ascii_org_names() -> None:
    """Organization names from various scripts."""
    assert ascii_text("Газпром ПАО") == "Gazprom PAO"
    assert ascii_text("Société Générale") == "Societe Generale"


# --- latinize_text ---


def test_latinize_ukrainian_poroshenko() -> None:
    """latinize_text preserves diacritics, unlike ascii_text."""
    assert (
        latinize_text("Порошенко Петро Олексійович")
        == "Porošenko Petro Oleksíjovič"
    )


def test_latinize_russian() -> None:
    assert latinize_text("Владимир Путин") == "Vladimir Putin"


def test_latinize_greek() -> None:
    assert (
        latinize_text("Κυριάκος Μητσοτάκης")
        == "Kyriákos Mētsotákēs"
    )


def test_latinize_chinese() -> None:
    """Chinese to Pinyin with tone marks."""
    assert latinize_text("习近平") == "xí jìn píng"


def test_latinize_georgian() -> None:
    assert latinize_text("ნინო ბურჯანაძე") == "nino burjanadze"
