// Port of `rigour.text.numbers.string_number`. Converts a numeric string
// to an `f64`, handling Unicode digit scripts (Arabic-Indic, Devanagari,
// fullwidth, …), CJK numerals (一二三, 萬), Roman numerals in the
// dedicated U+2160 block, and vulgar fractions (½, ¼, …).
//
// ## Contract
//
// Returns `Some(value)` if the whole string parses unambiguously; `None`
// otherwise. No partial parsing, no error values, no special handling of
// leading signs beyond what `f64::from_str` accepts.
//
// ## Multi-character rules
//
// The Python implementation had a latent bug: its "multiply by 10 per
// char" loop mis-handled mixed inputs (`"3½" → 30.5`) and multi-glyph
// Roman runs (`"ⅯⅮⅭ" → 105100`). This port fixes that:
//
//   - A single-character input with any defined numeric value returns
//     that value directly: `"Ⅻ" → 12`, `"½" → 0.5`, `"萬" → 10000`.
//   - A multi-character input only accumulates if every character is a
//     plain integer 0..10 digit. Covers Arabic-Indic / Devanagari /
//     fullwidth digit runs and CJK per-digit strings like `"一二三"`.
//     Rejects `"3½"`, `"ⅯⅮⅭ"`, and any other mixed or multi-letter
//     input.
//
// ## Range coverage
//
// - ASCII digits via `char::to_digit(10)` and `f64::from_str` fast path.
// - Non-ASCII decimal digit blocks (Unicode category `Nd`): hard-coded
//   list of per-block zero offsets, covers the common scripts plus
//   fullwidth. If a new `Nd` block becomes relevant, add its zero to
//   `ND_ZEROES`.
// - Roman numerals: U+2160..U+2188 (category `Nl`) only. Latin ASCII
//   `M`/`D`/`C`/`L`/`X`/`V`/`I` have no Unicode `Numeric_Value` and are
//   not recognised — intentional. "MCMLXXXIV" → None, not 1984.
// - Vulgar fractions: U+00BC..U+00BE and U+2150..U+215F.
// - CJK: 〇 一 二 三 四 五 六 七 八 九 十 廿 卅 百 千 萬 億 兆. Enough to
//   cover realistic name-part inputs like `"萬"` (10000) or `"五百"`
//   as a single token when that comes up.

/// Parse `text` into an f64 using the rules described at the top of this
/// file. Returns `None` for empty input, mixed inputs, or strings
/// containing any char with no defined numeric value.
pub fn string_number(text: &str) -> Option<f64> {
    if text.is_empty() {
        return None;
    }

    // Fast path: ASCII int/float (including signs, decimal point, e-notation).
    let raw = if let Ok(v) = text.parse::<f64>() {
        Some(v)
    } else {
        // Per-char numeric lookup. If any char lacks a value, bail.
        let values: Vec<f64> = text
            .chars()
            .map(numeric_value)
            .collect::<Option<Vec<_>>>()?;

        if values.len() == 1 {
            Some(values[0])
        } else if values
            .iter()
            .all(|&v| v.fract() == 0.0 && (0.0..10.0).contains(&v))
        {
            // Multi-character: only plain 0..10 integer digits accumulate.
            // Rejects "3½" (3 + 0.5), "ⅯⅮⅭ" (1000+500+100), mixed Nd+Nl.
            Some(values.iter().fold(0.0, |acc, &v| acc * 10.0 + v))
        } else {
            None
        }
    };

    // Guard against inf / NaN: very long digit runs overflow f64 to
    // infinity, and some exotic ASCII inputs parse as NaN ("nan",
    // "inf", "-inf"). Treat these as unparseable — f64 silently
    // swallows overflow but the caller expects a real number.
    raw.filter(|v| v.is_finite())
}

/// Numeric value of a single char, or `None` if it has no Unicode
/// Numeric_Value (or isn't in the covered ranges). Mirrors Python's
/// `unicodedata.numeric(c)` for the subset of characters we care about.
fn numeric_value(c: char) -> Option<f64> {
    // ASCII 0–9 (also hit via the fast path on whole-string parse, but
    // this is needed for per-char multi-digit scans like "42" where the
    // fast path already succeeded, and for mixed-script inputs).
    if let Some(d) = c.to_digit(10) {
        return Some(d as f64);
    }

    let cu = c as u32;

    // Non-ASCII Nd blocks: each is a contiguous 0..9 run.
    for &zero in ND_ZEROES {
        if cu >= zero && cu < zero + 10 {
            return Some((cu - zero) as f64);
        }
    }

    // Everything below is a single-codepoint explicit lookup.
    match c {
        // Vulgar fractions (U+00BC..U+00BE)
        '\u{00BC}' => Some(0.25),
        '\u{00BD}' => Some(0.5),
        '\u{00BE}' => Some(0.75),

        // Roman numerals U+2160..U+216F (uppercase I..M)
        '\u{2160}' => Some(1.0),    // Ⅰ
        '\u{2161}' => Some(2.0),    // Ⅱ
        '\u{2162}' => Some(3.0),    // Ⅲ
        '\u{2163}' => Some(4.0),    // Ⅳ
        '\u{2164}' => Some(5.0),    // Ⅴ
        '\u{2165}' => Some(6.0),    // Ⅵ
        '\u{2166}' => Some(7.0),    // Ⅶ
        '\u{2167}' => Some(8.0),    // Ⅷ
        '\u{2168}' => Some(9.0),    // Ⅸ
        '\u{2169}' => Some(10.0),   // Ⅹ
        '\u{216A}' => Some(11.0),   // Ⅺ
        '\u{216B}' => Some(12.0),   // Ⅻ
        '\u{216C}' => Some(50.0),   // Ⅼ
        '\u{216D}' => Some(100.0),  // Ⅽ
        '\u{216E}' => Some(500.0),  // Ⅾ
        '\u{216F}' => Some(1000.0), // Ⅿ
        // Roman numerals U+2170..U+217F (lowercase i..m)
        '\u{2170}' => Some(1.0),
        '\u{2171}' => Some(2.0),
        '\u{2172}' => Some(3.0),
        '\u{2173}' => Some(4.0),
        '\u{2174}' => Some(5.0),
        '\u{2175}' => Some(6.0),
        '\u{2176}' => Some(7.0),
        '\u{2177}' => Some(8.0),
        '\u{2178}' => Some(9.0),
        '\u{2179}' => Some(10.0),
        '\u{217A}' => Some(11.0),
        '\u{217B}' => Some(12.0),
        '\u{217C}' => Some(50.0),
        '\u{217D}' => Some(100.0),
        '\u{217E}' => Some(500.0),
        '\u{217F}' => Some(1000.0),
        // Archaic Roman (U+2180..U+2188)
        '\u{2180}' => Some(1000.0),
        '\u{2181}' => Some(5000.0),
        '\u{2182}' => Some(10000.0),
        '\u{2183}' => Some(100.0), // Roman Numeral Reversed Hundred
        '\u{2185}' => Some(6.0),
        '\u{2186}' => Some(50.0),
        '\u{2187}' => Some(50000.0),
        '\u{2188}' => Some(100000.0),

        // More vulgar fractions U+2150..U+215F
        '\u{2150}' => Some(1.0 / 7.0),
        '\u{2151}' => Some(1.0 / 9.0),
        '\u{2152}' => Some(1.0 / 10.0),
        '\u{2153}' => Some(1.0 / 3.0),
        '\u{2154}' => Some(2.0 / 3.0),
        '\u{2155}' => Some(1.0 / 5.0),
        '\u{2156}' => Some(2.0 / 5.0),
        '\u{2157}' => Some(3.0 / 5.0),
        '\u{2158}' => Some(4.0 / 5.0),
        '\u{2159}' => Some(1.0 / 6.0),
        '\u{215A}' => Some(5.0 / 6.0),
        '\u{215B}' => Some(1.0 / 8.0),
        '\u{215C}' => Some(3.0 / 8.0),
        '\u{215D}' => Some(5.0 / 8.0),
        '\u{215E}' => Some(7.0 / 8.0),
        // U+215F is "FRACTION NUMERATOR ONE" (1/) — not a standalone value.

        // CJK numerals. Only the forms that realistically appear as
        // standalone tokens in name data.
        '〇' => Some(0.0),
        '一' | '壹' => Some(1.0),
        '二' | '貳' | '贰' => Some(2.0),
        '三' | '參' | '叁' => Some(3.0),
        '四' | '肆' => Some(4.0),
        '五' | '伍' => Some(5.0),
        '六' | '陸' | '陆' => Some(6.0),
        '七' | '柒' => Some(7.0),
        '八' | '捌' => Some(8.0),
        '九' | '玖' => Some(9.0),
        '十' | '拾' => Some(10.0),
        '廿' => Some(20.0),
        '卅' => Some(30.0),
        '百' | '佰' => Some(100.0),
        '千' | '仟' => Some(1000.0),
        '萬' | '万' => Some(10000.0),
        '億' | '亿' => Some(100000000.0),
        '兆' => Some(1_000_000_000_000.0),

        _ => None,
    }
}

/// Unicode codepoint of each 0 in a contiguous 0..9 decimal-digit
/// block. Adding a new block is a one-line change — the Unicode Nd
/// blocks that matter for our corpus are listed here.
const ND_ZEROES: &[u32] = &[
    0x0660, // Arabic-Indic
    0x06F0, // Extended Arabic-Indic
    0x07C0, // NKo
    0x0966, // Devanagari
    0x09E6, // Bengali
    0x0A66, // Gurmukhi
    0x0AE6, // Gujarati
    0x0B66, // Oriya
    0x0BE6, // Tamil
    0x0C66, // Telugu
    0x0CE6, // Kannada
    0x0D66, // Malayalam
    0x0DE6, // Sinhala Lith
    0x0E50, // Thai
    0x0ED0, // Lao
    0x0F20, // Tibetan
    0x1040, // Myanmar
    0x1090, // Myanmar Shan
    0x17E0, // Khmer
    0x1810, // Mongolian
    0x1946, // Limbu
    0x19D0, // New Tai Lue
    0x1A80, // Tai Tham Hora
    0x1A90, // Tai Tham Tham
    0x1B50, // Balinese
    0x1BB0, // Sundanese
    0x1C40, // Lepcha
    0x1C50, // Ol Chiki
    0xA620, // Vai
    0xA8D0, // Saurashtra
    0xA900, // Kayah Li
    0xA9D0, // Javanese
    0xA9F0, // Myanmar Tai Laing
    0xAA50, // Cham
    0xABF0, // Meetei Mayek
    0xFF10, // Fullwidth
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ascii_ints_and_floats() {
        assert_eq!(string_number("0"), Some(0.0));
        assert_eq!(string_number("42"), Some(42.0));
        assert_eq!(string_number("-42"), Some(-42.0));
        assert_eq!(string_number("2.5"), Some(2.5));
        assert_eq!(string_number("1e3"), Some(1000.0));
    }

    #[test]
    fn rejects_empty_and_non_numeric() {
        assert_eq!(string_number(""), None);
        assert_eq!(string_number("abc"), None);
        assert_eq!(string_number("!"), None);
        assert_eq!(string_number("1a"), None);
    }

    #[test]
    fn arabic_indic_digits() {
        assert_eq!(string_number("\u{0664}\u{0665}\u{0666}"), Some(456.0));
    }

    #[test]
    fn extended_arabic_indic_digits() {
        assert_eq!(string_number("\u{06F1}\u{06F2}\u{06F3}"), Some(123.0));
    }

    #[test]
    fn devanagari_digits() {
        assert_eq!(string_number("\u{0967}\u{0968}\u{0969}"), Some(123.0));
    }

    #[test]
    fn fullwidth_digits() {
        assert_eq!(string_number("\u{FF11}\u{FF12}\u{FF13}"), Some(123.0));
    }

    #[test]
    fn roman_numeral_single_char() {
        assert_eq!(string_number("\u{216B}"), Some(12.0)); // Ⅻ
        assert_eq!(string_number("\u{216F}"), Some(1000.0)); // Ⅿ
        assert_eq!(string_number("\u{217B}"), Some(12.0)); // ⅻ
    }

    #[test]
    fn roman_numeral_multi_char_rejected() {
        // "ⅯⅮⅭ" would be 1600 in proper Roman notation, but our rule
        // rejects multi-char Nl runs — 1000, 500, 100 are not 0..10
        // digits. Python's pre-port impl returned 105100 here.
        assert_eq!(string_number("\u{216F}\u{216E}\u{216D}"), None);
    }

    #[test]
    fn latin_letters_not_roman() {
        // ASCII "M"/"D"/"C" have no Unicode Numeric_Value — only the
        // dedicated U+2160+ glyphs do. Reject Latin letters.
        assert_eq!(string_number("M"), None);
        assert_eq!(string_number("MCMLXXXIV"), None);
        assert_eq!(string_number("XII"), None);
    }

    #[test]
    fn vulgar_fractions_single_char() {
        assert_eq!(string_number("\u{00BD}"), Some(0.5));
        assert_eq!(string_number("\u{00BC}"), Some(0.25));
        assert_eq!(string_number("\u{00BE}"), Some(0.75));
    }

    #[test]
    fn digit_plus_fraction_rejected() {
        // "3½" — Python pre-port returned 30.5 (3*10 + 0.5). This port
        // rejects it: the `½` value 0.5 isn't a 0..10 integer, so the
        // multi-char accumulation short-circuits.
        assert_eq!(string_number("3\u{00BD}"), None);
        assert_eq!(string_number("1\u{00BD}"), None);
    }

    #[test]
    fn cjk_single_char() {
        assert_eq!(string_number("萬"), Some(10000.0));
        assert_eq!(string_number("億"), Some(100000000.0));
        assert_eq!(string_number("十"), Some(10.0));
    }

    #[test]
    fn cjk_per_digit_run() {
        // 一二三 = 1, 2, 3 — all 0..10 integers, so the accumulation
        // path fires: (1)*10+2=12, *10+3=123.
        assert_eq!(string_number("一二三"), Some(123.0));
        assert_eq!(string_number("九九九"), Some(999.0));
    }

    #[test]
    fn cjk_mixed_rejected() {
        // "萬五" — 10000 and 5 mixed; 10000 isn't a 0..10 digit, bail.
        assert_eq!(string_number("萬五"), None);
    }

    #[test]
    fn overflow_to_infinity_rejected() {
        // f64 silently overflows to inf somewhere around 308 digits.
        // The caller expects a real number, not inf — return None.
        let huge = "1".repeat(400);
        assert_eq!(string_number(&huge), None);
        // Same via the CJK accumulation path.
        let huge_cjk = "九".repeat(400);
        assert_eq!(string_number(&huge_cjk), None);
    }

    #[test]
    fn nan_and_inf_literals_rejected() {
        // f64::from_str accepts these; we don't.
        assert_eq!(string_number("inf"), None);
        assert_eq!(string_number("-inf"), None);
        assert_eq!(string_number("NaN"), None);
        assert_eq!(string_number("nan"), None);
    }
}
