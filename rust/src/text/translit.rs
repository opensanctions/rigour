// Rigour's public transliteration surface: `should_ascii` +
// `maybe_ascii`. Deliberately narrow — covers only the 6 scripts
// `LATINIZE_SCRIPTS` admits (Latin, Cyrillic, Greek, Armenian,
// Georgian, Hangul). Anything outside that set passes through
// unchanged (or becomes empty, depending on the `drop` flag).
//
// For broader-script lossy romanisation (Han, Arabic, Thai,
// Devanagari, etc.) callers use `normality.ascii_text` /
// `normality.latinize_text` directly. rigour does not try to
// duplicate that surface.

use icu::experimental::transliterate::Transliterator;
use icu::locale::Locale;
use icu::normalizer::{ComposingNormalizerBorrowed, DecomposingNormalizerBorrowed};
use icu::properties::{CodePointMapData, props::GeneralCategory};
use lru::LruCache;
use std::cell::RefCell;
use std::collections::HashMap;
use std::num::NonZeroUsize;
use std::sync::{LazyLock, Mutex};

use crate::constants::MEMO_LARGE;
use crate::text::scripts::text_scripts;

// Script long names admitted by `should_ascii`. Single source of
// truth for the admission policy — the Python side has no mirror;
// `rigour.text.scripts.can_latinize` forwards to `should_ascii`.
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

// Per-thread by necessity, not choice: `Transliterator` embeds
// `Box<dyn CustomTransliterator>` without a `Send` bound, so it can't
// live in a process-global static. Six constructions per thread is an
// acceptable price; the result memo below is global.
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
    ('Ɔ', "O"), // open O
    ('ƍ', "d"), // turned delta
    ('Ǝ', "E"), // turned E (uppercase; ǝ already below)
    ('Ɣ', "G"), // gamma
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
    // --- IPA Extensions letters that occur in names.
    ('ɔ', "o"), // open o (Akan, Ewe)
    ('ɣ', "g"), // gamma
    ('ʕ', ""),  // ʿayin in Arabic romanizations
];

// Letters substituted before a script's ICU4X pass, where the source
// letter is still known. ISO-9 style output (`ш → š`, `я → â`) would
// otherwise strip to a bare letter that no common ASCII spelling uses,
// and fixing it after the pass would also hit native Latin `š` (Czech
// `Škoda`). Keys are lowercase; `apply_prepass` restores case.
#[derive(Clone, Copy, PartialEq)]
enum At {
    Any,
    WordStart,
    WordEnd,
}

type Rules = &'static [(&'static str, At, &'static str)];

struct PrePass {
    // The first matching rule wins, so positional rules must precede
    // `At::Any` rules for the same key.
    rules: Rules,
    // Language-specific rules for words containing any of the marker
    // letters, taking precedence over `rules`.
    variants: &'static [(&'static str, Rules)],
    // Drop accents (but not the diaeresis) before matching, so `ή`
    // matches the `η` rule.
    strip_accents: bool,
    // Emit every letter lowercased, for scripts whose ICU4X
    // transliterator only knows the lowercase forms.
    fold_case: bool,
}

// `х → kh`, `є → ye` and `ї → yi` match fewer real spellings than the
// ICU4X output, so they are left out. `ь`/`ъ` would surface as `'`/`"`;
// the letters from `қ` on have no ASCII rendering in the ICU4X output.
const CYRILLIC_PREPASS: PrePass = PrePass {
    rules: &[
        ("ш", At::Any, "sh"),
        ("ч", At::Any, "ch"),
        ("щ", At::Any, "shch"),
        ("ж", At::Any, "zh"),
        ("ц", At::Any, "ts"),
        ("я", At::Any, "ya"),
        ("ю", At::Any, "yu"),
        ("ё", At::Any, "yo"),
        ("й", At::Any, "i"),
        ("ий", At::WordEnd, "y"),
        ("ый", At::WordEnd, "y"),
        ("ь", At::Any, ""),
        ("ъ", At::Any, ""),
        ("ђ", At::Any, "dj"),
        ("џ", At::Any, "dz"),
        ("љ", At::Any, "lj"),
        ("њ", At::Any, "nj"),
        ("ѓ", At::Any, "gj"),
        ("қ", At::Any, "q"),
        ("ҳ", At::Any, "h"),
        ("ҷ", At::Any, "j"),
        ("җ", At::Any, "j"),
        ("ҡ", At::Any, "k"),
        ("ӏ", At::Any, ""),
        ("ӡ", At::Any, "dz"),
        ("ҭ", At::Any, "t"),
        ("ҫ", At::Any, "s"),
        ("ӷ", At::Any, "g"),
        ("ӿ", At::Any, "h"),
        ("ѣ", At::Any, "e"),
        ("ѳ", At::Any, "f"),
        ("ѵ", At::Any, "i"),
        ("ѹ", At::Any, "u"),
        ("ѧ", At::Any, "ya"),
        ("ѡ", At::Any, "o"),
    ],
    variants: &[
        // Serbian / Macedonian: ASCII spellings follow the Latin
        // orthography with its diacritics dropped (`Milošević`).
        (
            "ђћџљњјѓќѕ",
            &[
                ("ш", At::Any, "s"),
                ("ч", At::Any, "c"),
                ("ж", At::Any, "z"),
                ("ц", At::Any, "c"),
            ],
        ),
        // Ukrainian / Belarusian.
        ("іїєґў", &[("г", At::Any, "h"), ("и", At::Any, "y")]),
    ],
    strip_accents: false,
    fold_case: false,
};

// Modern (ELOT 743) spellings where CLDR gives the classical ones
// (`β → b`, `η → ē`, `φ → ph`).
const GREEK_PREPASS: PrePass = PrePass {
    rules: &[
        ("β", At::Any, "v"),
        ("η", At::Any, "i"),
        ("φ", At::Any, "f"),
        ("μπ", At::WordStart, "b"),
        ("ντ", At::WordStart, "d"),
        ("γκ", At::WordStart, "g"),
        ("μπ", At::Any, "mb"),
        ("γκ", At::Any, "ng"),
        ("αυ", At::Any, "av"),
        ("ευ", At::Any, "ev"),
    ],
    variants: &[],
    strip_accents: true,
    fold_case: false,
};

// CLDR marks ejectives with an apostrophe (`კ → kʼ`) that ASCII
// spellings drop. Mtavruli capitals (`Კ`) fold to Mkhedruli, which is
// all the ICU4X transliterator covers.
const GEORGIAN_PREPASS: PrePass = PrePass {
    rules: &[
        ("კ", At::Any, "k"),
        ("პ", At::Any, "p"),
        ("ტ", At::Any, "t"),
        ("წ", At::Any, "ts"),
        ("ჭ", At::Any, "ch"),
        ("ყ", At::Any, "k"),
    ],
    variants: &[],
    strip_accents: false,
    fold_case: true,
};

// CLDR marks aspirates with `ʻ` (`թ → tʻ`), which surfaces as `'`.
const ARMENIAN_PREPASS: PrePass = PrePass {
    rules: &[
        ("շ", At::Any, "sh"),
        ("չ", At::Any, "ch"),
        ("ճ", At::Any, "ch"),
        ("ժ", At::Any, "zh"),
        ("խ", At::Any, "kh"),
        ("ց", At::Any, "ts"),
        ("ծ", At::Any, "ts"),
        ("ղ", At::Any, "gh"),
        ("ձ", At::Any, "dz"),
        ("թ", At::Any, "t"),
        ("ք", At::Any, "k"),
        ("փ", At::Any, "p"),
        ("ՙ", At::Any, ""),
    ],
    variants: &[],
    strip_accents: false,
    fold_case: false,
};

fn prepass_for_script(script: &str) -> Option<&'static PrePass> {
    match script {
        "Cyrillic" => Some(&CYRILLIC_PREPASS),
        "Greek" => Some(&GREEK_PREPASS),
        "Georgian" => Some(&GEORGIAN_PREPASS),
        "Armenian" => Some(&ARMENIAN_PREPASS),
        _ => None,
    }
}

fn to_lower(c: char) -> char {
    let mut lower = c.to_lowercase();
    match (lower.next(), lower.next()) {
        (Some(l), None) => l,
        _ => c,
    }
}

fn strip_accents(input: &str) -> String {
    let gc = CodePointMapData::<GeneralCategory>::new();
    let decomposed: String = DecomposingNormalizerBorrowed::new_nfd()
        .normalize(input)
        .chars()
        .filter(|c| *c == '\u{0308}' || gc.get(*c) != GeneralCategory::NonspacingMark)
        .collect();
    ComposingNormalizerBorrowed::new_nfc()
        .normalize(&decomposed)
        .into_owned()
}

fn match_rule(
    rules: Rules,
    low: &[char],
    i: usize,
    word: (usize, usize),
) -> Option<(usize, &'static str)> {
    rules.iter().find_map(|(key, at, repl)| {
        let n = key.chars().count();
        let fits = i + n <= word.1
            && key.chars().eq(low[i..i + n].iter().copied())
            && match at {
                At::Any => true,
                At::WordStart => i == word.0,
                At::WordEnd => i + n == word.1,
            };
        fits.then_some((n, *repl))
    })
}

// Case a replacement after the source span `chars[start..start + len]`:
// all caps when the neighbouring letter (the next one, or the previous
// one at a word end) is uppercase, so `ШЕВЧЕНКО → SHEVCHENKO`; title
// case otherwise, so `Шевченко → Shevchenko`.
fn push_cased(out: &mut String, repl: &str, chars: &[char], start: usize, len: usize) {
    if !chars[start].is_uppercase() {
        out.push_str(repl);
        return;
    }
    let neighbour = chars
        .get(start + len)
        .filter(|c| c.is_alphabetic())
        .or_else(|| {
            start
                .checked_sub(1)
                .and_then(|p| chars.get(p))
                .filter(|c| c.is_alphabetic())
        });
    if neighbour.is_some_and(|c| c.is_uppercase()) {
        out.push_str(&repl.to_ascii_uppercase());
        return;
    }
    let mut rest = repl.chars();
    if let Some(first) = rest.next() {
        out.push(first.to_ascii_uppercase());
        out.push_str(rest.as_str());
    }
}

fn apply_prepass(input: &str, pass: &PrePass) -> String {
    let stripped;
    let input = if pass.strip_accents {
        stripped = strip_accents(input);
        stripped.as_str()
    } else {
        input
    };
    let low: Vec<char> = input.chars().map(to_lower).collect();
    let chars: Vec<char> = if pass.fold_case {
        low.clone()
    } else {
        input.chars().collect()
    };
    let mut out = String::with_capacity(input.len() + 8);
    let mut i = 0;
    while i < chars.len() {
        if !chars[i].is_alphabetic() {
            out.push(chars[i]);
            i += 1;
            continue;
        }
        let start = i;
        let end = (i..chars.len())
            .find(|j| !chars[*j].is_alphabetic())
            .unwrap_or(chars.len());
        let variant = pass
            .variants
            .iter()
            .find(|(markers, _)| low[start..end].iter().any(|c| markers.contains(*c)))
            .map(|(_, rules)| *rules);
        while i < end {
            let found = variant
                .and_then(|rules| match_rule(rules, &low, i, (start, end)))
                .or_else(|| match_rule(pass.rules, &low, i, (start, end)));
            match found {
                Some((n, repl)) => {
                    push_cased(&mut out, repl, &chars, i, n);
                    i += n;
                }
                None => {
                    out.push(chars[i]);
                    i += 1;
                }
            }
        }
    }
    out
}

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

// Process-global LRU of `maybe_ascii` results, probed before any ICU
// work. `None` records the not-admitted verdict, so repeated Han /
// Arabic / etc. inputs skip the script scan too; the `drop` flag is
// applied at return time, letting both drop modes share one entry
// (past the admission check the pipeline output doesn't depend on
// `drop`). Guarded by a Mutex: `py_maybe_ascii` holds the GIL, so
// stock CPython never contends on it.
static MAYBE_ASCII_CACHE: LazyLock<Mutex<LruCache<String, Option<String>>>> =
    LazyLock::new(|| Mutex::new(LruCache::new(NonZeroUsize::new(MEMO_LARGE).unwrap())));

/// If every distinguishing script in `text` is in
/// `LATINIZE_SCRIPTS`, transliterate to ASCII via a layered pipeline:
///
/// 1. **Per-script pass** (Cyrillic → Latin, Greek → Latin, etc.) —
///    non-Latin scripts go through their ICU4X transliterator to
///    produce Latin output. Latin input skips this step. A per-script
///    pre-pass first substitutes common ASCII spellings for letters
///    ICU4X renders in a scholarly form (`Шевченко → Shevchenko`, not
///    `Sevcenko`); native Latin diacritics still fold (`Škoda → Skoda`).
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
    if let Some(cached) = MAYBE_ASCII_CACHE.lock().unwrap().get(text).cloned() {
        return match cached {
            Some(result) => result,
            None if drop => String::new(),
            None => text.to_string(),
        };
    }
    let scripts = text_scripts(text);
    if scripts.iter().any(|s| !LATINIZE_SCRIPTS.contains(s)) {
        MAYBE_ASCII_CACHE
            .lock()
            .unwrap()
            .put(text.to_string(), None);
        return if drop {
            String::new()
        } else {
            text.to_string()
        };
    }
    // Pre-pass keys are composed letters (`й`, not `и` + breve).
    let mut result = ComposingNormalizerBorrowed::new_nfc()
        .normalize(text)
        .into_owned();
    for script in scripts {
        if script == "Latin" {
            continue;
        }
        if let Some(pass) = prepass_for_script(script) {
            result = apply_prepass(&result, pass);
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
    MAYBE_ASCII_CACHE
        .lock()
        .unwrap()
        .put(text.to_string(), Some(result.clone()));
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
        // No digraphs for native Latin diacritics.
        assert_eq!(maybe_ascii("Škoda", false), "Skoda");
        assert_eq!(maybe_ascii("Milošević", false), "Milosevic");
        assert_eq!(maybe_ascii("Şahin", false), "Sahin");
        assert_eq!(maybe_ascii("Ștefan", false), "Stefan");
        assert_eq!(maybe_ascii("Țiriac", false), "Tiriac");
    }

    #[test]
    fn maybe_ascii_latin_fallback_table() {
        assert_eq!(maybe_ascii("Lars Løkke", false), "Lars Lokke");
        assert_eq!(maybe_ascii("weißbier", false), "weissbier");
        assert_eq!(maybe_ascii("Əhməd", false), "Ahmad");
        assert_eq!(maybe_ascii("Kɔfi", false), "Kofi");
        assert_eq!(maybe_ascii("aɣa", false), "aga");
        assert_eq!(maybe_ascii("ʕAli", false), "Ali");
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
        assert_eq!(maybe_ascii("Владимир", false), "Vladimir");
        assert_eq!(maybe_ascii("Шевченко", false), "Shevchenko");
        assert_eq!(maybe_ascii("Щукин", false), "Shchukin");
        assert_eq!(maybe_ascii("Жуков", false), "Zhukov");
        assert_eq!(maybe_ascii("Цой", false), "Tsoi");
        assert_eq!(maybe_ascii("Яценюк", false), "Yatsenyuk");
        assert_eq!(maybe_ascii("Зеленский", false), "Zelensky");
        assert_eq!(maybe_ascii("Ґудзь", false), "Gudz");
    }

    #[test]
    fn maybe_ascii_cyrillic_languages() {
        assert_eq!(maybe_ascii("Гіркін", false), "Hirkin");
        assert_eq!(maybe_ascii("Милошевић", false), "Milosevic");
        assert_eq!(maybe_ascii("Љубљана", false), "Ljubljana");
        assert_eq!(maybe_ascii("Ђоковић", false), "Djokovic");
        assert_eq!(maybe_ascii("Џеко", false), "Dzeko");
        assert_eq!(maybe_ascii("Қазақстан", false), "Qazaqstan");
        assert_eq!(maybe_ascii("Җәлил", false), "Jalil");
        assert_eq!(maybe_ascii("Нохчӏийчоь", false), "Nohchiicho");
        assert_eq!(maybe_ascii("Ѳеодоръ", false), "Feodor");
    }

    #[test]
    fn maybe_ascii_decomposed_input() {
        let nfd = |s: &str| {
            DecomposingNormalizerBorrowed::new_nfd()
                .normalize(s)
                .into_owned()
        };
        assert_eq!(maybe_ascii(&nfd("Зеленский"), false), "Zelensky");
        assert_eq!(maybe_ascii(&nfd("Ёлкин"), false), "Yolkin");
    }

    #[test]
    fn maybe_ascii_prepass_case() {
        assert_eq!(maybe_ascii("ШЕВЧЕНКО", false), "SHEVCHENKO");
        assert_eq!(maybe_ascii("ЗЕЛЕНСКИЙ", false), "ZELENSKY");
        assert_eq!(maybe_ascii("ЦОЙ", false), "TSOI");
        assert_eq!(maybe_ascii("Ж. Ш.", false), "Zh. Sh.");
        assert_eq!(maybe_ascii("ΜΠΑΛΤΑΣ", false), "BALTAS");
    }

    #[test]
    fn maybe_ascii_greek() {
        assert_eq!(maybe_ascii("Αθήνα", false), "Athina");
        assert_eq!(maybe_ascii("Βασίλης", false), "Vasilis");
        assert_eq!(maybe_ascii("Φίλιππος", false), "Filippos");
        assert_eq!(maybe_ascii("Μπαλτάς", false), "Baltas");
        assert_eq!(maybe_ascii("Λάμπρος", false), "Lambros");
        assert_eq!(maybe_ascii("Ντόρα", false), "Dora");
        assert_eq!(maybe_ascii("Γκίκας", false), "Gikas");
        assert_eq!(maybe_ascii("Ευάγγελος", false), "Evangelos");
    }

    #[test]
    fn maybe_ascii_armenian() {
        assert_eq!(maybe_ascii("Միթչել", false), "Mitchel");
        assert_eq!(maybe_ascii("Ղուկասյան", false), "Ghukasyan");
        assert_eq!(maybe_ascii("Քոչարյան", false), "Kocharyan");
        assert_eq!(maybe_ascii("Փաշինյան", false), "Pashinyan");
    }

    #[test]
    fn maybe_ascii_georgian() {
        assert_eq!(maybe_ascii("ნინო", false), "nino");
        assert_eq!(maybe_ascii("კედელაშვილი", false), "kedelashvili");
        assert_eq!(maybe_ascii("წერეთელი", false), "tsereteli");
        assert_eq!(maybe_ascii("ჭავჭავაძე", false), "chavchavadze");
        assert_eq!(maybe_ascii("ყიფიანი", false), "kipiani");
        assert_eq!(maybe_ascii("ᲙᲔᲓᲔᲚᲐᲨᲕᲘᲚᲘ", false), "kedelashvili");
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
    fn maybe_ascii_drop_variants_share_cache_entry() {
        // Both drop modes are served from one cached not-admitted
        // verdict; the flag is applied at return time and must not
        // leak the other mode's output.
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

    #[test]
    fn maybe_ascii_non_latin_roundtrip() {
        // Every letter of the admitted non-Latin alphabets, plus the
        // regional Cyrillic letters the pre-pass handles, must come out
        // as ASCII letters. `ь`/`ъ`, palochka and the Armenian modifier
        // `ՙ` are dropped on purpose.
        const RANGES: &[(char, char)] = &[
            ('\u{0410}', '\u{044F}'), // Russian А–я
            ('\u{0391}', '\u{03A1}'), // Greek Α–Ρ
            ('\u{03A3}', '\u{03A9}'), // Greek Σ–Ω
            ('\u{03B1}', '\u{03C9}'), // Greek α–ω
            ('\u{0531}', '\u{0556}'), // Armenian capitals
            ('\u{0561}', '\u{0586}'), // Armenian small
            ('\u{10D0}', '\u{10F0}'), // Georgian Mkhedruli
            ('\u{1C90}', '\u{1CB0}'), // Georgian Mtavruli
        ];
        const EXTRA: &str = "ёЁіІїЇєЄґҐўЎђЂћЋџЏљЉњЊјЈѓЃќЌѕЅқҚҳҲҷҶҗҖҡҠӡӠҭҬҫҪӷӶӿӾѣѢѳѲѵѴѹѸѧѦѡѠ";
        const DROPPED: &[char] = &['ь', 'Ь', 'ъ', 'Ъ', 'ӏ', 'Ӏ', 'ՙ'];
        let misses: Vec<(char, String)> = RANGES
            .iter()
            .flat_map(|(lo, hi)| *lo..=*hi)
            .chain(EXTRA.chars())
            .filter(|c| !DROPPED.contains(c))
            .map(|c| (c, maybe_ascii(&c.to_string(), false)))
            .filter(|(_, out)| out.is_empty() || !out.chars().all(|o| o.is_ascii_alphanumeric()))
            .collect();
        assert!(misses.is_empty(), "non-letter output: {misses:?}");
    }
}
