// Rigour's public transliteration surface: `should_ascii` +
// `maybe_ascii`. Deliberately narrow — covers only the 6 scripts
// `rigour.text.scripts.LATINIZE_SCRIPTS` admits (Latin, Cyrillic,
// Greek, Armenian, Georgian, Hangul). Anything outside that set
// passes through unchanged (or becomes empty, depending on the
// `drop` flag).
//
// For broader-script lossy romanisation (Han, Arabic, Thai,
// Devanagari, etc.) callers use `normality.ascii_text` /
// `normality.latinize_text` directly. rigour does not try to
// duplicate that surface.

use icu::experimental::transliterate::Transliterator;
use icu::locale::Locale;
use icu::normalizer::DecomposingNormalizerBorrowed;
use icu::properties::{CodePointMapData, props::GeneralCategory};
use lru::LruCache;
use std::cell::RefCell;
use std::collections::HashMap;
use std::num::NonZeroUsize;

use crate::constants::MEMO_LARGE;
use crate::text::scripts::text_scripts;

// Script long names admitted by `should_ascii`. Mirrors
// `rigour.text.scripts.LATINIZE_SCRIPTS` (`rigour/text/scripts.py:10`).
// Latin is trivially admitted (identity transliterator, covered by
// the ASCII fast-path); the other five each have an ICU4X
// transliterator below.
const LATINIZE_SCRIPTS: &[&str] = &[
    "Latin", "Cyrillic", "Greek", "Armenian", "Georgian", "Hangul",
];

// BCP-47-T locale IDs for the 5 non-Latin scripts in
// `LATINIZE_SCRIPTS`. Latin is absent from this per-script table
// because Latin input needs no script-to-Latin transliteration;
// however it still goes through `LATIN_ASCII_LOCALE` below to
// strip Latin Extended letters (ĸ, ĳ, ɓ, ƙ, etc.) that NFKD can't
// decompose.
const SCRIPT_LOCALES: &[(&str, &str)] = &[
    ("Cyrillic", "und-Latn-t-und-cyrl"),
    ("Greek", "und-Latn-t-und-grek"),
    ("Armenian", "und-Latn-t-und-armn"),
    ("Georgian", "und-Latn-t-und-geor"),
    ("Hangul", "und-Latn-t-und-hang"),
];

// CLDR's Latin-ASCII transliterator, baked into icu_experimental_data.
// Applied unconditionally after the per-script pass so Latin Extended
// input (never processed by the per-script loop) and Latin-Extended
// residue from the per-script loop (e.g. Greek → Latin emits
// diacritics) both get simplified to ASCII where CLDR has a rule.
// Letters CLDR leaves intact (schwa Ə/ə, …) are caught by the
// subsequent NFKD + strip-marks + `ASCII_FALLBACK` tail.
const LATIN_ASCII_LOCALE: &str = "und-t-und-latn-d0-ascii";

fn locale_for_script(script: &str) -> Option<&'static str> {
    SCRIPT_LOCALES
        .iter()
        .find(|(s, _)| *s == script)
        .map(|(_, loc)| *loc)
}

thread_local! {
    static TRANSLITERATOR_CACHE: RefCell<HashMap<&'static str, Option<Transliterator>>> =
        RefCell::new(HashMap::new());
}

fn transliterate_with(locale_id: &'static str, input: String) -> String {
    TRANSLITERATOR_CACHE.with(|cache| {
        let mut cache = cache.borrow_mut();
        if !cache.contains_key(locale_id) {
            let t = locale_id
                .parse::<Locale>()
                .ok()
                .and_then(|locale| Transliterator::try_new(&locale).ok());
            cache.insert(locale_id, t);
        }
        match cache.get(locale_id).expect("just-inserted entry exists") {
            Some(t) => t.transliterate(input),
            None => input,
        }
    })
}

// Non-decomposable Latin diacritics that NFKD won't break apart,
// plus modifier letters and CJK-adjacent punctuation ICU4X's
// per-script transliterators emit in their Latin output.
const ASCII_FALLBACK: &[(char, &str)] = &[
    ('æ', "ae"),
    ('Æ', "AE"),
    ('œ', "oe"),
    ('Œ', "OE"),
    ('ø', "o"),
    ('Ø', "O"),
    ('ß', "ss"),
    ('ẞ', "SS"),
    ('ə', "a"),
    ('Ə', "A"),
    ('ı', "i"),
    ('İ', "I"),
    ('ł', "l"),
    ('Ł', "L"),
    ('đ', "d"),
    ('Đ', "D"),
    ('ð', "d"),
    ('Ð', "D"),
    ('þ', "th"),
    ('Þ', "Th"),
    ('ħ', "h"),
    ('Ħ', "H"),
    ('ŋ', "ng"),
    ('Ŋ', "NG"),
    // ICU4X's Cyrillic transliterator emits MODIFIER LETTER PRIME /
    // DOUBLE PRIME for the soft/hard sign per ISO 9. Fold to ASCII
    // punctuation for output compatibility with PyICU-trained
    // matchers downstream.
    ('\u{02B9}', "'"),  // ʹ MODIFIER LETTER PRIME (soft sign ь)
    ('\u{02BA}', "\""), // ʺ MODIFIER LETTER DOUBLE PRIME (hard sign ъ)
    ('\u{02BB}', "'"),
    ('\u{02BC}', "'"),
    ('\u{02BD}', "'"),
    ('\u{02BE}', "'"),
    ('\u{02BF}', "'"),
    ('\u{02C8}', "'"),
    ('\u{02CA}', "'"),
    ('\u{02CB}', "'"),
    // Catalan `Ŀ`/`ŀ` (U+013F/0140) NFKD-decompose to `L·`/`l·`; the
    // middle dot is Punctuation, skips both LA and mark-strip. Drop it
    // once we're confident we're on the latinization path (this table
    // only runs after `should_ascii`).
    ('\u{00B7}', ""),
    // --- CORE Latin ranges: Africanist / IPA / medievalist letters
    // CLDR Latin-ASCII leaves alone. Conventional ASCII mappings for
    // name-matching purposes. See `maybe_ascii_latin_roundtrip` test
    // for the authoritative source of this list.
    ('Ƅ', "B"),
    ('ƅ', "b"), // tone six
    ('Ɔ', "O"), // open O (uppercase; ɔ → o is CLDR)
    ('ƍ', "d"), // turned delta
    ('Ǝ', "E"), // turned E (uppercase; ǝ already below)
    ('Ɣ', "G"), // gamma (uppercase; ɣ handled by CLDR)
    ('ƛ', "l"), // lambda with stroke
    ('Ɯ', "M"), // turned M (uppercase)
    ('Ɵ', "O"), // barred O (uppercase)
    ('Ʀ', "R"), // small-cap R
    ('Ƨ', "S"),
    ('ƨ', "s"), // tone two
    ('Ʃ', "S"), // esh (uppercase)
    ('ƪ', "l"), // reversed esh loop
    ('Ʊ', "U"), // Latin upsilon (uppercase)
    ('Ʒ', "Z"),
    ('ʒ', "z"), // ezh (also resolves `Ǯ → Ʒ` / `ǯ → ʒ`)
    ('Ƹ', "Z"),
    ('ƹ', "z"), // reversed ezh
    ('ƺ', "z"), // ezh with tail
    ('ƻ', "2"), // two with stroke
    ('Ƽ', "5"),
    ('ƽ', "5"), // tone five
    ('ƾ', ""),  // inverted glottal stop with stroke
    ('ƿ', "w"), // wynn
    ('ǀ', ""),
    ('ǁ', ""), // Khoisan clicks — drop; no informative ASCII
    ('ǂ', ""),
    ('ǃ', ""),
    ('ǝ', "e"), // turned e (lowercase)
    ('Ƕ', "Hv"),
    ('Ƿ', "W"), // hwair, wynn (Old English/Gothic)
    ('Ȝ', "Y"),
    ('ȝ', "y"), // yogh (Middle English)
    ('Ƞ', "N"), // N with long right leg
    ('Ȣ', "Ou"),
    ('ȣ', "ou"), // OU ligature (Huron/Wyandot)
    ('Ɂ', ""),
    ('ɂ', ""),  // glottal stop
    ('Ʌ', "V"), // turned V (uppercase; ʌ already in IPA block)
    ('Ɋ', "Q"),
    ('ɋ', "q"), // Q with hook tail
    ('ẟ', "d"), // small Latin delta (Latin Extended Additional)
];

fn ascii_fallback(input: &str) -> String {
    if input.is_ascii() {
        return input.to_string();
    }
    let mut out = String::with_capacity(input.len());
    for ch in input.chars() {
        if ch.is_ascii() {
            out.push(ch);
            continue;
        }
        match ASCII_FALLBACK.iter().find(|(c, _)| *c == ch) {
            Some((_, repl)) => out.push_str(repl),
            None => out.push(ch),
        }
    }
    out
}

fn nfkd_strip_marks(input: &str) -> String {
    let nfkd = DecomposingNormalizerBorrowed::new_nfkd();
    let decomposed = nfkd.normalize(input);
    let gc = CodePointMapData::<GeneralCategory>::new();
    decomposed
        .chars()
        .filter(|c| gc.get(*c) != GeneralCategory::NonspacingMark)
        .collect()
}

/// True iff every distinguishing script in `text` is in
/// `LATINIZE_SCRIPTS` (Latin, Cyrillic, Greek, Armenian, Georgian,
/// Hangul). Pure-punct / pure-digit / empty inputs return true
/// vacuously — `text_scripts` filters out Common/Inherited.
pub fn should_ascii(text: &str) -> bool {
    for script in text_scripts(text) {
        if !LATINIZE_SCRIPTS.contains(&script) {
            return false;
        }
    }
    true
}

// LRU of `maybe_ascii` results. Keyed on `(drop, text)` so the two
// drop modes don't poison each other's cache lines — for a given
// input they produce different outputs.
thread_local! {
    static MAYBE_ASCII_CACHE: RefCell<LruCache<(bool, String), String>> = RefCell::new(
        LruCache::new(NonZeroUsize::new(MEMO_LARGE).unwrap())
    );
}

/// If every distinguishing script in `text` is in
/// `LATINIZE_SCRIPTS`, transliterate to ASCII via a layered pipeline:
///
/// 1. **Per-script pass** (Cyrillic → Latin, Greek → Latin, etc.) —
///    non-Latin scripts go through their ICU4X transliterator to
///    produce Latin output. Latin input skips this step.
/// 2. **NFKD + nonspacing-mark strip** — decomposes base+combiner
///    sequences (é → e + acute → e) and resolves compatibility
///    variants (modifier letter ʱ → ɦ, superscript ᵋ → ɛ).
/// 3. **CLDR Latin-ASCII pass** — applied unconditionally. Handles
///    Latin Extended letters (`ĸ → q`, `ĳ → ij`, `ƙ → k`, `ɓ → b`,
///    …) including the simplified base letters surfaced by step 2.
/// 4. **`ASCII_FALLBACK`** — rigour's opinionated overrides for
///    cases where CLDR's Latin-ASCII keeps a non-ASCII letter
///    (e.g. Azerbaijani schwa `Ə → A`, African uppercase IPA letters
///    `Ʒ → Z`, `Ɔ → O`, …).
///
/// The ordering matters: NFKD before Latin-ASCII lets CLDR's rules
/// act on the decomposed base letters rather than being stopped by
/// compatibility wrappers.
///
/// If any script is outside `LATINIZE_SCRIPTS`, return `text`
/// unchanged (when `drop == false`) or `""` (when `drop == true`).
///
/// Pure-ASCII input bypasses the ICU4X pipeline entirely.
pub fn maybe_ascii(text: &str, drop: bool) -> String {
    if text.is_ascii() {
        return text.to_string();
    }
    if !should_ascii(text) {
        return if drop {
            String::new()
        } else {
            text.to_string()
        };
    }
    let key_text = text.to_string();
    if let Some(cached) =
        MAYBE_ASCII_CACHE.with(|c| c.borrow_mut().get(&(drop, key_text.clone())).cloned())
    {
        return cached;
    }
    let mut result = text.to_string();
    for script in text_scripts(text) {
        if script == "Latin" {
            continue;
        }
        if let Some(locale_id) = locale_for_script(script) {
            result = transliterate_with(locale_id, result);
        }
    }
    // NFKD first — compatibility decompositions turn modifier letters
    // and superscript Latin variants into their base letters (e.g.
    // ʱ → ɦ, ᵋ → ɛ). Running Latin-ASCII afterwards catches the
    // simplified base where CLDR has a rule.
    result = nfkd_strip_marks(&result);
    result = transliterate_with(LATIN_ASCII_LOCALE, result);
    result = ascii_fallback(&result);
    MAYBE_ASCII_CACHE.with(|c| {
        c.borrow_mut().put((drop, key_text), result.clone());
    });
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- should_ascii ---

    #[test]
    fn should_ascii_admits_latinize_scripts() {
        assert!(should_ascii("hello"));
        assert!(should_ascii("Владимир"));
        assert!(should_ascii("Αθήνα"));
        assert!(should_ascii("Միթչել"));
        assert!(should_ascii("ნინო"));
        assert!(should_ascii("김민석"));
    }

    #[test]
    fn should_ascii_rejects_non_latinize() {
        assert!(!should_ascii("中国"));
        assert!(!should_ascii("日本"));
        assert!(!should_ascii("بشار"));
        assert!(!should_ascii("สวัสดี"));
        assert!(!should_ascii("नमस्ते"));
    }

    #[test]
    fn should_ascii_handles_mixed_scripts() {
        // Latin + Cyrillic — both admitted
        assert!(should_ascii("Hello мир"));
        // Latin + Han — Han rejects
        assert!(!should_ascii("Tokyo東京"));
    }

    #[test]
    fn should_ascii_vacuous_cases() {
        // Empty, pure-punct, pure-digit — text_scripts returns
        // nothing, all() is vacuously true.
        assert!(should_ascii(""));
        assert!(should_ascii("   "));
        assert!(should_ascii("123"));
        assert!(should_ascii("!@#$%"));
        assert!(should_ascii("2024-12-31"));
    }

    // --- maybe_ascii: admitted scripts ---

    #[test]
    fn maybe_ascii_pure_ascii_passthrough() {
        assert_eq!(maybe_ascii("hello", false), "hello");
        assert_eq!(maybe_ascii("hello", true), "hello");
        assert_eq!(maybe_ascii("", false), "");
    }

    #[test]
    fn maybe_ascii_latin_diacritics() {
        assert_eq!(maybe_ascii("café", false), "cafe");
        assert_eq!(maybe_ascii("naïve", false), "naive");
        assert_eq!(maybe_ascii("Zürich", false), "Zurich");
    }

    #[test]
    fn maybe_ascii_latin_fallback_table() {
        assert_eq!(maybe_ascii("Lars Løkke", false), "Lars Lokke");
        assert_eq!(maybe_ascii("weißbier", false), "weissbier");
        assert_eq!(maybe_ascii("Əhməd", false), "Ahmad");
    }

    #[test]
    fn maybe_ascii_latin_extended_residue_cases() {
        // The original panic trigger: U+0138 KRA mid-string.
        let out = maybe_ascii("ALAĸSANDRAVIC", false);
        assert!(out.is_ascii(), "{out}");
        assert_eq!(out.to_lowercase(), "alaqsandravic");
        // Dutch ij ligature.
        assert_eq!(maybe_ascii("ĳsselmeer", false), "ijsselmeer");
        assert_eq!(maybe_ascii("Ĳsselmeer", false), "IJsselmeer");
        // Africanist / medievalist letters handled by CLDR or fallback.
        assert!(maybe_ascii("ƙarshe", false).is_ascii());
        assert!(maybe_ascii("ɓolo", false).is_ascii());
        assert!(maybe_ascii("Ɓolo", false).is_ascii());
        assert!(maybe_ascii("Ǝkwu", false).is_ascii());
        assert!(maybe_ascii("Ʒandarma", false).is_ascii());
        // Catalan geminate middle dot is stripped.
        assert_eq!(maybe_ascii("paraŀlel", false), "parallel");
    }

    #[test]
    fn maybe_ascii_cyrillic() {
        let out = maybe_ascii("Владимир", false);
        assert!(out.is_ascii(), "{out}");
        assert!(out.to_lowercase().contains("vladimir"), "{out}");
    }

    #[test]
    fn maybe_ascii_greek() {
        let out = maybe_ascii("Αθήνα", false);
        assert!(out.is_ascii(), "{out}");
    }

    #[test]
    fn maybe_ascii_armenian() {
        let out = maybe_ascii("Միթչել", false);
        assert!(out.is_ascii(), "{out}");
    }

    #[test]
    fn maybe_ascii_georgian() {
        let out = maybe_ascii("ნინო", false);
        assert!(out.is_ascii(), "{out}");
    }

    #[test]
    fn maybe_ascii_hangul() {
        let out = maybe_ascii("김민석", false);
        assert!(out.is_ascii(), "{out}");
    }

    // --- maybe_ascii: non-admitted scripts ---

    #[test]
    fn maybe_ascii_keeps_non_latinizable_when_drop_false() {
        assert_eq!(maybe_ascii("中国", false), "中国");
        assert_eq!(maybe_ascii("日本", false), "日本");
        assert_eq!(maybe_ascii("بشار", false), "بشار");
        assert_eq!(maybe_ascii("สวัสดี", false), "สวัสดี");
    }

    #[test]
    fn maybe_ascii_drops_non_latinizable_when_drop_true() {
        assert_eq!(maybe_ascii("中国", true), "");
        assert_eq!(maybe_ascii("日本", true), "");
        assert_eq!(maybe_ascii("بشار", true), "");
    }

    // --- maybe_ascii: mixed-script cases ---

    #[test]
    fn maybe_ascii_mixed_latin_cyrillic() {
        // Latin + Cyrillic — both admitted, transliterates fully
        let out = maybe_ascii("Hello мир", false);
        assert!(out.is_ascii(), "{out}");
        assert!(out.starts_with("Hello "), "{out}");
    }

    #[test]
    fn maybe_ascii_mixed_with_rejected_script() {
        // Latin + Han — Han rejects, whole string kept/dropped per flag
        assert_eq!(maybe_ascii("Tokyo東京", false), "Tokyo東京");
        assert_eq!(maybe_ascii("Tokyo東京", true), "");
    }

    #[test]
    fn maybe_ascii_vacuous_passthrough() {
        // text_scripts empty → should_ascii true → ASCII fast-path
        // already handled these, but verify the whole chain.
        assert_eq!(maybe_ascii("2024-12-31", false), "2024-12-31");
        assert_eq!(maybe_ascii("!@#", false), "!@#");
    }

    // --- caching sanity ---

    #[test]
    fn maybe_ascii_cache_roundtrip_consistent() {
        // Same input called twice should produce identical output,
        // even though the second call hits the cache.
        let first = maybe_ascii("Владимир", false);
        let second = maybe_ascii("Владимир", false);
        assert_eq!(first, second);
    }

    #[test]
    fn maybe_ascii_drop_variants_cached_separately() {
        // drop=true and drop=false for the same non-Latinizable
        // input produce different outputs; cache must not alias.
        assert_eq!(maybe_ascii("中国", false), "中国");
        assert_eq!(maybe_ascii("中国", true), "");
        // Call again to exercise cached code paths.
        assert_eq!(maybe_ascii("中国", false), "中国");
        assert_eq!(maybe_ascii("中国", true), "");
    }

    // --- Latin-script round-trip coverage ---

    #[test]
    fn maybe_ascii_latin_roundtrip() {
        // Every codepoint in the "core" Latin blocks — those that
        // realistically appear in real-world name data — must
        // round-trip through `maybe_ascii` to pure ASCII. Blocks
        // outside this range (IPA Extensions, Phonetic Extensions,
        // Latin Extended-C/D/E/F, Letterlike Symbols, etc.) carry
        // symbols that don't show up in names; leaving them as non-
        // ASCII residue is an accepted gap — downstream code that
        // cares (e.g. `metaphone`) guards against non-ASCII input
        // directly.
        //
        // Any failure here is a forced conversation: add an
        // `ASCII_FALLBACK` entry or expand the excluded ranges with
        // explicit justification.
        use crate::text::scripts::codepoint_script;
        const CORE_LATIN_RANGES: &[(u32, u32)] = &[
            (0x0080, 0x00FF), // Latin-1 Supplement
            (0x0100, 0x017F), // Latin Extended-A
            (0x0180, 0x024F), // Latin Extended-B
            (0x1E00, 0x1EFF), // Latin Extended Additional (Vietnamese-heavy)
            (0xFB00, 0xFB06), // Latin Ligatures
        ];
        let gc = CodePointMapData::<GeneralCategory>::new();
        let mut misses: Vec<(u32, char, String)> = Vec::new();
        for (lo, hi) in CORE_LATIN_RANGES {
            for cp in *lo..=*hi {
                let ch = match char::from_u32(cp) {
                    Some(c) => c,
                    None => continue,
                };
                if codepoint_script(cp) != Some("Latin") {
                    continue;
                }
                // `text_scripts` only reports scripts for Letter /
                // Number category codepoints; mirror that so the test
                // covers what real inputs actually exercise.
                let category = gc.get(ch);
                let is_letter = matches!(
                    category,
                    GeneralCategory::UppercaseLetter
                        | GeneralCategory::LowercaseLetter
                        | GeneralCategory::TitlecaseLetter
                        | GeneralCategory::ModifierLetter
                        | GeneralCategory::OtherLetter
                );
                let is_number = matches!(
                    category,
                    GeneralCategory::DecimalNumber
                        | GeneralCategory::LetterNumber
                        | GeneralCategory::OtherNumber
                );
                if !is_letter && !is_number {
                    continue;
                }
                let input = ch.to_string();
                let output = maybe_ascii(&input, false);
                if !output.is_ascii() {
                    misses.push((cp, ch, output));
                }
            }
        }
        if !misses.is_empty() {
            eprintln!(
                "{} core-Latin codepoint(s) did not round-trip to ASCII:",
                misses.len()
            );
            for (cp, ch, out) in &misses {
                eprintln!("  U+{:04X} {:?} -> {:?}", cp, ch, out);
            }
            panic!("Latin-ASCII round-trip coverage incomplete");
        }
    }
}
