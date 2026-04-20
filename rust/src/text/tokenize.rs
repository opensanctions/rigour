// Port of `rigour.names.tokenize.tokenize_name` — splits a name string
// into tokens using Unicode General Category as the separator rule.
//
// Parity target: `rigour/names/tokenize.py`. The Python side keeps a
// memoised `str.translate()` table (`_TokenizerLookup`) because per-
// codepoint `unicodedata.category()` lookups over FFI-ish paths are
// expensive. In Rust we just consult ICU's `CodePointMapData` directly
// on each char — compiled_data is in-memory, look-ups are O(1), and
// a single pass over the string is fast enough that a per-codepoint
// cache would only add overhead.
//
// The mapping is the same as Python's `TOKEN_SEP_CATEGORIES` dict:
//
//   Whitespace (token separator): Cc, Zs, Zl, Zp, Pc, Pd, Ps, Pe,
//                                 Pi, Pf, Po, Sm, So
//   Delete:                       Cf, Co, Cn, Lm*, Mn, Me, No, Sc, Sk
//   Keep:                         everything else (L*, Nd, Nl, Mc)
//
//   * Lm is deleted EXCEPT for a small set of CJK marks listed in
//     KEEP_CHARS (prolonged-sound marks, ideographic iteration mark).
//   * SKIP_CHARS (dot + apostrophe/prime/accent variants) are always
//     deleted, even though some of those codepoints have a category
//     that would otherwise map to whitespace. Matches Python's
//     pre-seeded None entries in `_TokenizerLookup`.

use icu::properties::{CodePointMapData, props::GeneralCategory};

use crate::text::normalize::CharAction;

// Characters deleted outright — punctuation inside abbreviations
// ("U.S.A." → "USA") and apostrophe-like marks inside names
// ("O'Brien" → "OBrien"). Mirrors `SKIP_CHARACTERS` in
// rigour/names/tokenize.py.
const SKIP_CHARS: &[char] = &[
    '.',        // U+002E FULL STOP
    '\u{0027}', // APOSTROPHE
    '\u{2018}', // LEFT SINGLE QUOTATION MARK
    '\u{2019}', // RIGHT SINGLE QUOTATION MARK
    '\u{02BC}', // MODIFIER LETTER APOSTROPHE
    '\u{02B9}', // MODIFIER LETTER PRIME
    '\u{0060}', // GRAVE ACCENT
    '\u{00B4}', // ACUTE ACCENT
];

// Lm (Modifier Letter) characters that carry meaning in real CJK
// names and must not be deleted. Mirrors `KEEP_CHARACTERS` in the
// Python source.
const KEEP_CHARS: &[char] = &[
    '\u{30FC}', // KATAKANA-HIRAGANA PROLONGED SOUND MARK (ー)
    '\u{FF70}', // HALFWIDTH KATAKANA-HIRAGANA PROLONGED SOUND MARK (ｰ)
    '\u{3005}', // IDEOGRAPHIC ITERATION MARK (々)
];

fn category_action(cat: GeneralCategory) -> CharAction {
    use GeneralCategory::*;
    match cat {
        // Whitespace / token separator
        Control => CharAction::Whitespace, // Cc
        SpaceSeparator | LineSeparator | ParagraphSeparator => CharAction::Whitespace, // Zs/Zl/Zp
        ConnectorPunctuation | DashPunctuation | OpenPunctuation | ClosePunctuation
        | InitialPunctuation | FinalPunctuation | OtherPunctuation => CharAction::Whitespace, // Pc/Pd/Ps/Pe/Pi/Pf/Po
        MathSymbol | OtherSymbol => CharAction::Whitespace, // Sm/So

        // Delete — invisible/format chars, combining marks, modifier
        // letters (KEEP_CHARS override applied in the caller before
        // this lookup), other numbers, currency and modifier symbols.
        Format | PrivateUse | Unassigned => CharAction::Delete, // Cf/Co/Cn
        ModifierLetter => CharAction::Delete,                   // Lm
        NonspacingMark | EnclosingMark => CharAction::Delete,   // Mn/Me
        OtherNumber => CharAction::Delete,                      // No
        CurrencySymbol | ModifierSymbol => CharAction::Delete,  // Sc/Sk

        // Keep: L* (Ll/Lu/Lt/Lo), Nd, Nl, Mc (Brahmic/Indic vowel
        // signs), and anything else ICU might classify outside the
        // explicit buckets above. Mc is an intentional keep — see the
        // comment on TOKEN_SEP_CATEGORIES in the Python source.
        _ => CharAction::Keep,
    }
}

/// Split `text` into tokens using Unicode category-based separation.
/// `token_min_length` counts codepoints (matching Python `len()`),
/// not bytes.
///
/// Single pass: classify each char into Keep/Delete/Whitespace, append
/// to a scratch buffer, then split on ASCII whitespace and filter by
/// length. The classification lookup (`CodePointMapData::get`) is
/// cheap enough that re-doing it on every call is faster than
/// maintaining a per-process memo table.
pub fn tokenize_name(text: &str, token_min_length: usize) -> Vec<String> {
    let gc = CodePointMapData::<GeneralCategory>::new();
    let mut buf = String::with_capacity(text.len());

    for ch in text.chars() {
        // SKIP_CHARS and KEEP_CHARS override the category lookup.
        // Both sets are tiny so linear scan beats a HashSet.
        if SKIP_CHARS.contains(&ch) {
            continue;
        }
        if KEEP_CHARS.contains(&ch) {
            buf.push(ch);
            continue;
        }
        match category_action(gc.get(ch)) {
            CharAction::Keep => buf.push(ch),
            CharAction::Delete => {}
            CharAction::Whitespace => buf.push(' '),
        }
    }

    buf.split_whitespace()
        .filter(|t| t.chars().count() >= token_min_length)
        .map(|s| s.to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tok(s: &str) -> Vec<String> {
        tokenize_name(s, 1)
    }

    #[test]
    fn basic_latin() {
        assert_eq!(tok("John Doe"), vec!["John", "Doe"]);
        assert_eq!(tok("Bond, James Bond"), vec!["Bond", "James", "Bond"]);
        assert_eq!(tok("Bashar al-Assad"), vec!["Bashar", "al", "Assad"]);
    }

    #[test]
    fn skip_chars_deleted() {
        assert_eq!(tok("O\u{0027}Brien"), vec!["OBrien"]);
        assert_eq!(tok("O\u{2019}Brien"), vec!["OBrien"]);
        assert_eq!(tok("O\u{2018}Brien"), vec!["OBrien"]);
        assert_eq!(tok("O\u{02BC}Brien"), vec!["OBrien"]);
        assert_eq!(tok("C.I.A."), vec!["CIA"]);
        assert_eq!(tok("U.S.A."), vec!["USA"]);
        assert_eq!(tok("..."), Vec::<String>::new());
    }

    #[test]
    fn min_length_filter() {
        assert_eq!(tokenize_name("Bashar al-Assad", 3), vec!["Bashar", "Assad"]);
        assert_eq!(tokenize_name("foo", 4), Vec::<String>::new());
    }

    #[test]
    fn empty_and_whitespace() {
        assert_eq!(tok(""), Vec::<String>::new());
        assert_eq!(tok("---"), Vec::<String>::new());
        assert_eq!(tok("foo  bar"), vec!["foo", "bar"]);
        assert_eq!(tok(" foo "), vec!["foo"]);
    }

    #[test]
    fn unicode_categories() {
        assert_eq!(tok("foo\x00bar"), vec!["foo", "bar"]); // Cc → WS
        assert_eq!(tok("foo\u{200B}bar"), vec!["foobar"]); // Cf (ZWSP) → deleted
        assert_eq!(tok("a+b"), vec!["a", "b"]); // Sm → WS
        assert_eq!(tok("$100"), vec!["100"]); // Sc → deleted
        assert_eq!(tok("n\u{0308}"), vec!["n"]); // Mn → deleted
    }

    #[test]
    fn zero_width_chars_deleted() {
        assert_eq!(tok("foo\u{200C}bar"), vec!["foobar"]); // ZWNJ
        assert_eq!(tok("foo\u{200D}bar"), vec!["foobar"]); // ZWJ
        assert_eq!(tok("foo\u{200F}bar"), vec!["foobar"]); // RTL mark
        assert_eq!(tok("foo\u{200E}bar"), vec!["foobar"]); // LTR mark
    }

    #[test]
    fn combining_marks_deleted() {
        assert_eq!(tok("re\u{0301}sume\u{0301}"), vec!["resume"]);
    }

    #[test]
    fn arabic() {
        assert_eq!(tok("بشار الأسد"), vec!["بشار", "الأسد"]);
    }

    #[test]
    fn chinese_middle_dot() {
        // Middle dots are Po → token separator. Character outputs are
        // the same as the Python test fixture.
        assert_eq!(
            tok("维克托·亚历山德罗维奇·卢卡申科"),
            vec!["维克托", "亚历山德罗维奇", "卢卡申科"]
        );
    }

    #[test]
    fn cjk_no_spaces() {
        assert_eq!(tok("习近平"), vec!["习近平"]);
        assert_eq!(tok("김민석"), vec!["김민석"]);
    }

    #[test]
    fn fullwidth_punctuation_splits() {
        assert_eq!(tok("田中！太郎"), vec!["田中", "太郎"]);
        assert_eq!(tok("東京，日本"), vec!["東京", "日本"]);
    }

    #[test]
    fn katakana_middle_dot_splits_but_prolonged_mark_kept() {
        // U+30FB KATAKANA MIDDLE DOT (Po) splits; U+30FC PROLONGED
        // SOUND MARK (Lm, in KEEP_CHARS) is kept inside tokens.
        assert_eq!(
            tok("ウラジーミル・プーチン"),
            vec!["ウラジーミル", "プーチン"]
        );
    }

    #[test]
    fn keep_chars_preserved() {
        assert_eq!(tok("ウラジーミル"), vec!["ウラジーミル"]); // ー
        assert_eq!(tok("佐々木"), vec!["佐々木"]); // 々
        assert_eq!(tok("野々村"), vec!["野々村"]);
        assert_eq!(tok("ｱｰﾄ"), vec!["ｱｰﾄ"]); // halfwidth ｰ
    }

    #[test]
    fn burmese_mc_kept_mn_deleted() {
        // Burmese: Mc (vowel signs) kept, Mn (asat etc.) deleted.
        // Matches the Python test's current behaviour.
        assert_eq!(tok("အောင်ဆန်းစုကြည်"), vec!["အောငဆနးစကြည"]);
    }
}
