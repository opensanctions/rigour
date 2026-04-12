from rigour.names import tokenize_name, normalize_name


def test_tokenize_name():
    assert tokenize_name("John Doe") == ["John", "Doe"]
    assert tokenize_name("Bond, James Bond") == ["Bond", "James", "Bond"]
    assert tokenize_name("C.I.A.") == ["CIA"]
    assert tokenize_name("Bashar al-Assad") == ["Bashar", "al", "Assad"]
    assert tokenize_name("Bashar al-Assad", token_min_length=3) == ["Bashar", "Assad"]
    assert tokenize_name("بشار الأسد") == ["بشار", "الأسد"]
    assert tokenize_name("维克托·亚历山德罗维奇·卢卡申科") == [
        "维克托",
        "亚历山德罗维奇",
        "卢卡申科",
    ]
    # Burmese: Mc (vowel signs) are now kept, but Mn (asat, etc.) are still deleted.
    # This is an improvement over the previous fragmented output but not yet correct.
    assert tokenize_name("အောင်ဆန်းစုကြည်") == ["အောငဆနးစကြည"]


def test_tokenize_skip_characters():
    assert tokenize_name("O\u0027Brien", token_min_length=1) == ["OBrien"]  # ASCII apostrophe
    assert tokenize_name("O\u2019Brien", token_min_length=1) == ["OBrien"]  # right single quote
    assert tokenize_name("O\u2018Brien", token_min_length=1) == ["OBrien"]  # left single quote
    assert tokenize_name("O\u02BCBrien", token_min_length=1) == ["OBrien"]  # modifier apostrophe
    assert tokenize_name("U.S.A.", token_min_length=1) == ["USA"]
    assert tokenize_name("...", token_min_length=1) == []


def test_tokenize_edge_cases():
    assert tokenize_name("", token_min_length=1) == []
    assert tokenize_name("---", token_min_length=1) == []
    assert tokenize_name("foo  bar", token_min_length=1) == ["foo", "bar"]
    assert tokenize_name(" foo ", token_min_length=1) == ["foo"]
    assert tokenize_name("foo", token_min_length=4) == []


def test_tokenize_unicode_categories():
    assert tokenize_name("foo\x00bar", token_min_length=1) == ["foo", "bar"]  # Cc -> WS
    assert tokenize_name("foo\u200bbar", token_min_length=1) == ["foobar"]  # Cf -> deleted
    assert tokenize_name("a+b", token_min_length=1) == ["a", "b"]  # Sm -> WS
    assert tokenize_name("$100", token_min_length=1) == ["100"]  # Sc -> deleted
    assert tokenize_name("n\u0308", token_min_length=1) == ["n"]  # Mn -> deleted


def test_normalize_name():
    assert normalize_name(None) is None
    assert normalize_name("") is None
    assert normalize_name("---") is None
    assert normalize_name("John Doe") == "john doe"


# --- Language-specific tokenization ---


def test_tokenize_spanish():
    """Spanish: double surname."""
    assert tokenize_name("maría garcía lópez") == ["maría", "garcía", "lópez"]


def test_tokenize_portuguese():
    """Portuguese: particle 'da'."""
    assert tokenize_name("luiz inácio lula da silva") == [
        "luiz", "inácio", "lula", "da", "silva",
    ]


def test_tokenize_scandinavian():
    """Scandinavian: diacritics preserved in tokens."""
    assert tokenize_name("göran persson") == ["göran", "persson"]
    assert tokenize_name("lars løkke rasmussen") == ["lars", "løkke", "rasmussen"]


def test_tokenize_hungarian():
    """Hungarian: surname-first order."""
    assert tokenize_name("orbán viktor") == ["orbán", "viktor"]


def test_tokenize_dutch_particles():
    """Dutch: particles 'van', 'der' as separate tokens."""
    assert tokenize_name("jan peter van der berg") == ["jan", "peter", "van", "der", "berg"]


def test_tokenize_baltic():
    """Lithuanian: diacritics preserved."""
    assert tokenize_name("dalia grybauskeitė") == ["dalia", "grybauskeitė"]


def test_tokenize_east_asian():
    """CJK: no spaces between characters, middle dots split tokens."""
    assert tokenize_name("习近平") == ["习近平"]
    assert tokenize_name("김민석") == ["김민석"]


# --- Punctuation edge cases ---


def test_tokenize_fullwidth_punctuation():
    """CJK fullwidth punctuation (Po category) should be token separators."""
    assert tokenize_name("田中！太郎") == ["田中", "太郎"]
    assert tokenize_name("東京，日本") == ["東京", "日本"]


def test_tokenize_middle_dot_variants():
    """Various middle dot characters used as name separators in CJK."""
    # U+00B7 MIDDLE DOT (used in Chinese transliterated names)
    assert tokenize_name("维克托·卢卡申科") == [
        "维克托", "卢卡申科",
    ]
    # U+30FB KATAKANA MIDDLE DOT (used in Japanese for foreign names)
    # Note: ー (prolonged sound mark, Lm) is preserved, ・ (middle dot, Po) splits
    assert tokenize_name("ウラジーミル・プーチン") == [
        "ウラジーミル", "プーチン",
    ]


def test_tokenize_keep_characters():
    """Specific Lm characters that carry meaning in CJK names are preserved."""
    # U+30FC KATAKANA-HIRAGANA PROLONGED SOUND MARK (ー)
    assert tokenize_name("ウラジーミル") == ["ウラジーミル"]
    # U+3005 IDEOGRAPHIC ITERATION MARK (々) — used in names like 佐々木 (Sasaki)
    assert tokenize_name("佐々木") == ["佐々木"]
    assert tokenize_name("野々村") == ["野々村"]
    # U+FF70 HALFWIDTH variant
    assert tokenize_name("ｱｰﾄ") == ["ｱｰﾄ"]


def test_tokenize_zero_width_chars():
    """Zero-width characters (Cf category) should be deleted, not split on."""
    assert tokenize_name("foo\u200cbar") == ["foobar"]  # ZWNJ
    assert tokenize_name("foo\u200dbar") == ["foobar"]  # ZWJ


def test_tokenize_combining_marks():
    """Combining diacritical marks (Mn category) should be deleted."""
    assert tokenize_name("re\u0301sume\u0301") == ["resume"]


def test_tokenize_rtl_marks():
    """RTL/LTR marks (Cf category) should be deleted."""
    assert tokenize_name("foo\u200fbar") == ["foobar"]  # RTL mark
    assert tokenize_name("foo\u200ebar") == ["foobar"]  # LTR mark
