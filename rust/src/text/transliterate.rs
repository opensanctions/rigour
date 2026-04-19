// ASCII / Latin transliteration via ICU4X.
//
// Two public functions:
//
// - `latinize_text(text)` — run the appropriate per-script transliterators
//   until everything's in Latin script. Diacritics (ø, ä, etc.) stay.
//
// - `ascii_text(text)` — latinize_text, then NFKD-decompose and strip
//   nonspacing marks, then apply a small fallback table for non-decomposable
//   diacritics (ø → o, ß → ss, ə → a, etc.).
//
// ICU4X's `compiled_data` ships per-script transliterators keyed by BCP-47-T
// locale IDs (`und-Latn-t-und-cyrl` etc.). It does NOT ship the compound
// `Any-Latin` transliterator, which is why we do the manual per-script
// dispatch here. The `Transliterator` type is `!Send + !Sync`, so we keep a
// thread-local cache of constructed ones — cheap init (~900µs per script)
// amortised over the thread's lifetime.

use icu::experimental::transliterate::Transliterator;
use icu::locale::Locale;
use icu::normalizer::DecomposingNormalizerBorrowed;
use icu::properties::{CodePointMapData, props::GeneralCategory};
use std::cell::RefCell;
use std::collections::HashMap;

use crate::text::scripts::text_scripts;

// Map from Unicode Script long name → BCP-47-T locale ID.
// Scripts not in this table pass through unchanged (input is returned as-is).
// Traditional Han falls back to Simplified's transliterator — good enough for
// name-matching purposes.
const SCRIPT_LOCALES: &[(&str, &str)] = &[
    ("Cyrillic", "und-Latn-t-und-cyrl"),
    ("Arabic", "und-Latn-t-und-arab"),
    ("Han", "und-Latn-t-und-hans"),
    ("Greek", "und-Latn-t-und-grek"),
    ("Hangul", "und-Latn-t-und-hang"),
    ("Georgian", "und-Latn-t-und-geor"),
    ("Armenian", "und-Latn-t-und-armn"),
    ("Devanagari", "und-Latn-t-und-deva"),
    ("Katakana", "und-Latn-t-und-kana"),
    ("Hiragana", "und-Latn-t-und-kana"), // Hiragana routes through Katakana
    ("Hebrew", "und-Latn-t-und-hebr"),
];

fn locale_for_script(script: &str) -> Option<&'static str> {
    SCRIPT_LOCALES
        .iter()
        .find(|(s, _)| *s == script)
        .map(|(_, loc)| *loc)
}

thread_local! {
    static TRANSLITERATOR_CACHE: RefCell<HashMap<&'static str, Transliterator>> =
        RefCell::new(HashMap::new());
}

fn transliterate_with(locale_id: &'static str, input: String) -> String {
    TRANSLITERATOR_CACHE.with(|cache| {
        let mut cache = cache.borrow_mut();
        if !cache.contains_key(locale_id) {
            let locale: Locale = locale_id.parse().expect("valid BCP-47-T locale");
            let t = Transliterator::try_new(&locale).expect("built-in transliterator present");
            cache.insert(locale_id, t);
        }
        let t = cache.get(locale_id).expect("just-inserted entry exists");
        t.transliterate(input)
    })
}

// Non-decomposable Latin diacritics that NFKD won't break apart. Keep this
// table small and curated — expand only when tests surface a real need.
// Ordered with longer replacements first to avoid accidental interactions
// (though .replace() semantics make order mostly irrelevant here).
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
];

fn ascii_fallback(input: &str) -> String {
    // Fast path: if the input is already ASCII, skip the char-by-char walk.
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

pub fn latinize_text(text: &str) -> String {
    if text.is_ascii() {
        return text.to_string();
    }
    let scripts = text_scripts(text);
    let mut result = text.to_string();
    for script in scripts {
        if script == "Latin" {
            continue;
        }
        if let Some(locale_id) = locale_for_script(script) {
            result = transliterate_with(locale_id, result);
        }
    }
    result
}

pub fn ascii_text(text: &str) -> String {
    if text.is_ascii() {
        return text.to_string();
    }
    let latin = latinize_text(text);
    let stripped = nfkd_strip_marks(&latin);
    ascii_fallback(&stripped)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn latinize_text_ascii_passthrough() {
        assert_eq!(latinize_text("hello"), "hello");
        assert_eq!(latinize_text(""), "");
    }

    #[test]
    fn latinize_text_cyrillic() {
        // Russian: Сергей → Sergei / Sergej (ICU4X convention)
        let out = latinize_text("Сергей");
        assert!(out.chars().all(|c| c.is_ascii() || c == 'ĭ' || c == 'j'));
        assert!(out.to_lowercase().starts_with("serge"));
    }

    #[test]
    fn latinize_text_greek() {
        let out = latinize_text("Αθήνα");
        // Should begin with some Latin-transliterated form of Athina
        assert!(out.chars().any(|c| c.is_ascii_alphabetic()));
        assert!(!out.chars().any(|c| ('\u{0370}'..='\u{03FF}').contains(&c)));
    }

    #[test]
    fn latinize_text_chinese() {
        let out = latinize_text("中国");
        // ICU4X Pinyin-ish output for China
        assert!(out.chars().any(|c| c.is_ascii_alphabetic()));
    }

    #[test]
    fn ascii_text_latin_diacritics_via_nfkd() {
        // "é" decomposes under NFKD into "e" + U+0301 (combining acute),
        // then mark stripping leaves just "e".
        assert_eq!(ascii_text("café"), "cafe");
        assert_eq!(ascii_text("naïve"), "naive");
        assert_eq!(ascii_text("Zürich"), "Zurich");
    }

    #[test]
    fn ascii_text_fallback_table() {
        // Non-decomposable diacritics: ø, ß, ə handled by the fallback table.
        assert_eq!(ascii_text("Lars Løkke Rasmussen"), "Lars Lokke Rasmussen");
        assert_eq!(ascii_text("weißbier"), "weissbier");
        assert_eq!(ascii_text("Əhməd"), "Ahmad");
    }

    #[test]
    fn ascii_text_cyrillic() {
        let out = ascii_text("Владимир");
        assert!(out.is_ascii());
        assert!(!out.is_empty());
    }

    #[test]
    fn ascii_text_mixed_scripts() {
        let out = ascii_text("Hello мир");
        assert!(out.is_ascii());
        assert!(out.to_lowercase().contains("hello"));
    }
}
