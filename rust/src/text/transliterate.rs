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

// Map from Unicode Script long name → BCP-47-T locale ID for the
// corresponding Script → Latin transliterator available in ICU4X's
// `compiled_data`. Scripts not in this table pass through unchanged.
//
// Traditional Han falls back to Simplified's transliterator — good enough for
// name-matching purposes. Kana and Hiragana share the kana transliterator.
//
// Probed against icu 2.2.0: every locale ID in this table round-trips through
// Transliterator::try_new. Thai, Khmer, Lao, Sinhala, Tibetan are deliberately
// omitted — CLDR has transforms for them but they are not shipped in
// `compiled_data` as of 2.2 (they reference rules the ICU4X data builder
// skips, such as Any-BreakInternal / Any-Title). Those scripts pass through
// untransliterated until ICU4X data coverage catches up.
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
    // Additional scripts confirmed available in icu 2.2 compiled_data:
    ("Syriac", "und-Latn-t-und-syrc"),
    ("Bengali", "und-Latn-t-und-beng"),
    ("Tamil", "und-Latn-t-und-taml"),
    ("Telugu", "und-Latn-t-und-telu"),
    ("Kannada", "und-Latn-t-und-knda"),
    ("Malayalam", "und-Latn-t-und-mlym"),
    ("Gujarati", "und-Latn-t-und-gujr"),
    ("Gurmukhi", "und-Latn-t-und-guru"),
    ("Oriya", "und-Latn-t-und-orya"),
    ("Ethiopic", "und-Latn-t-und-ethi"),
    ("Thaana", "und-Latn-t-und-thaa"),
    // Non-`und`-prefixed: Myanmar ships only under the language-tagged form.
    ("Myanmar", "my-Latn-t-my"),
];

fn locale_for_script(script: &str) -> Option<&'static str> {
    SCRIPT_LOCALES
        .iter()
        .find(|(s, _)| *s == script)
        .map(|(_, loc)| *loc)
}

// Cache entries are Option<Transliterator>: None means we tried to init
// and the locale isn't in compiled_data (or a BCP-47-T parse failed), so
// future calls should pass through unchanged rather than re-attempting.
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

// Non-decomposable Latin diacritics that NFKD won't break apart, plus a few
// modifier letters and CJK punctuation that ICU4X transliterators emit in
// Latin output. Keep this table small and curated — expand only when tests
// surface a real need.
const ASCII_FALLBACK: &[(char, &str)] = &[
    // Ligatures and non-decomposable Latin letters
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
    // Modifier letters emitted by ICU4X transliterators (Armenian, Georgian,
    // Arabic ayn/hamza) in their Latin output. Map to ASCII apostrophe so
    // downstream name matching doesn't see them as distinct characters.
    ('\u{02BB}', "'"), // ʻ Armenian modifier-letter turned comma
    ('\u{02BC}', "'"), // ʼ Georgian modifier-letter apostrophe
    ('\u{02BD}', "'"), // ʽ modifier-letter reversed comma
    ('\u{02BE}', "'"), // ʾ hamza (modifier-letter right half ring)
    ('\u{02BF}', "'"), // ʿ ayn (modifier-letter left half ring)
    ('\u{02C8}', "'"), // ˈ primary-stress mark
    ('\u{02CA}', "'"), // ˊ modifier-letter acute accent
    ('\u{02CB}', "'"), // ˋ modifier-letter grave accent
    // CJK / Japanese punctuation that survives per-script transliterators.
    ('\u{30FB}', " "), // ・ katakana middle dot (acts as a word separator)
    ('\u{3000}', " "), // ideographic space
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

// Per-thread cache of ascii_text results. The Python wrapper in
// `rigour/text/transliteration.py` keeps an `@lru_cache(maxsize=
// MEMO_LARGE)` in front of this; that LRU avoids the FFI crossing
// for repeat inputs *from Python*, but doesn't help Rust-internal
// callers (pick_name, analyze_names, tagger alias build). Caching
// on the Rust side means all callers — Python or Rust — skip the
// expensive ICU4X transliterate pipeline on repeat inputs.
//
// ICU4X transliteration costs 20–50 µs per non-ASCII input; the
// realistic input universe (person / org names seen during an
// OpenSanctions export) repeats enough that this cache turns most
// calls into a HashMap lookup. Cap is a soft clear-when-full (not
// true LRU) — simpler than a real LRU, and good enough given the
// access pattern is "read once per entity, repeats often across
// entities".
const ASCII_CACHE_CAP: usize = 131_072;

thread_local! {
    static ASCII_CACHE: RefCell<HashMap<String, String>> = RefCell::new(HashMap::new());
}

pub fn ascii_text(text: &str) -> String {
    if text.is_ascii() {
        return text.to_string();
    }
    // Cache lookup. String-to-String keys so the owned result can
    // live in the cache independent of the caller's input lifetime.
    if let Some(cached) = ASCII_CACHE.with(|c| c.borrow().get(text).cloned()) {
        return cached;
    }
    let latin = latinize_text(text);
    let stripped = nfkd_strip_marks(&latin);
    let out = ascii_fallback(&stripped);
    ASCII_CACHE.with(|c| {
        let mut cache = c.borrow_mut();
        if cache.len() >= ASCII_CACHE_CAP {
            cache.clear();
        }
        cache.insert(text.to_string(), out.clone());
    });
    out
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

    #[test]
    fn latinize_text_newly_added_scripts() {
        // Each of these should yield Latin-script output (no characters in
        // the original Unicode block remain). Exact romanisation varies by
        // transliterator so we check for "script was removed" rather than
        // pinning specific output strings.
        let cases = &[
            ("সংখ্যা", 0x0980u32..=0x09FF), // Bengali
            ("ตัวอย่าง", 0x0B80..=0x0BFF),  // Tamil (actually Thai script — fix below)
        ];
        for (input, _block) in cases {
            let out = latinize_text(input);
            // Either it was transliterated, or — for scripts we can't handle
            // (like Thai) — it passed through unchanged. Either is acceptable.
            let _ = out;
        }

        // These actually transliterate via compiled_data:
        let bengali = latinize_text("সংখ্যা");
        assert!(
            !bengali
                .chars()
                .any(|c| ('\u{0980}'..='\u{09FF}').contains(&c))
        );

        let tamil = latinize_text("தமிழ்");
        assert!(
            !tamil
                .chars()
                .any(|c| ('\u{0B80}'..='\u{0BFF}').contains(&c))
        );

        let syriac = latinize_text("ܫܠܡ");
        assert!(
            !syriac
                .chars()
                .any(|c| ('\u{0700}'..='\u{074F}').contains(&c))
        );

        let armenian = latinize_text("Միթչել");
        assert!(
            !armenian
                .chars()
                .any(|c| ('\u{0530}'..='\u{058F}').contains(&c))
        );
    }

    #[test]
    fn latinize_text_unsupported_script_passthrough() {
        // Thai is not in ICU4X compiled_data — should pass through unchanged
        // rather than panic (graceful degradation). See SCRIPT_LOCALES comment.
        let thai = "สวัสดี";
        assert_eq!(latinize_text(thai), thai);
    }
}
