// Flag-based text normalization. Replaces the `normalizer: Callable[[Optional[str]], Optional[str]]`
// callback pattern that rigour inherited from the normality library. See
// plans/rust-normalizer.md for the design rationale.
//
// `normalize(text, flags, cleanup)` runs the requested steps in a fixed
// pipeline order independent of bit order:
//
//   1. STRIP               — trim leading/trailing whitespace
//   2. NFKD / NFKC / NFC   — at most one is meaningful; later-declared wins
//   3. CASEFOLD            — Unicode full casefold (ß → ss, not lowercase)
//   4. ASCII or LATINIZE   — ASCII is a superset and wins if both are set
//   5. category_replace    — runs when `cleanup != Cleanup::Noop`
//   6. SQUASH_SPACES       — collapse runs of whitespace, trim ends
//
// Empty output → None, matching the Optional[str] contract of the legacy
// Python normalizers.

use bitflags::bitflags;
use icu::casemap::CaseMapper;
use icu::normalizer::{ComposingNormalizerBorrowed, DecomposingNormalizerBorrowed};
use icu::properties::{CodePointMapData, props::GeneralCategory};

use crate::text::transliterate::{ascii_text, latinize_text};

bitflags! {
    #[derive(Clone, Copy, Debug, PartialEq, Eq)]
    pub struct Normalize: u16 {
        const STRIP         = 1 << 0;
        const SQUASH_SPACES = 1 << 1;
        const CASEFOLD      = 1 << 2;
        const NFC           = 1 << 3;
        const NFKC          = 1 << 4;
        const NFKD          = 1 << 5;
        const LATINIZE      = 1 << 6;
        const ASCII         = 1 << 7;
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Cleanup {
    #[default]
    Noop,
    Strong,
    Slug,
}

enum CharAction {
    Keep,
    Delete,
    Whitespace,
}

// Strong — aggressive cleanup, matches normality.constants.UNICODE_CATEGORIES.
fn action_strong(cat: GeneralCategory) -> CharAction {
    use GeneralCategory::*;
    match cat {
        Control => CharAction::Whitespace, // Cc
        Format | Surrogate | PrivateUse | Unassigned => CharAction::Delete, // Cf/Cs/Co/Cn
        ModifierLetter | NonspacingMark | EnclosingMark => CharAction::Delete, // Lm/Mn/Me
        SpacingMark => CharAction::Whitespace, // Mc
        OtherNumber => CharAction::Delete, // No
        SpaceSeparator | LineSeparator | ParagraphSeparator => CharAction::Whitespace, // Zs/Zl/Zp
        ConnectorPunctuation | DashPunctuation | OpenPunctuation | ClosePunctuation
        | InitialPunctuation | FinalPunctuation | OtherPunctuation => CharAction::Whitespace, // Pc/Pd/Ps/Pe/Pi/Pf/Po
        MathSymbol => CharAction::Whitespace, // Sm
        CurrencySymbol | ModifierSymbol => CharAction::Delete, // Sc/Sk
        OtherSymbol => CharAction::Whitespace, // So
        _ => CharAction::Keep,                // Letters (except Lm) and numbers (Nd/Nl) kept
    }
}

// Slug — matches normality.constants.SLUG_CATEGORIES.
// Differences from Strong: Lm & Mn are kept (not deleted); Cc is deleted
// (not replaced with WS).
fn action_slug(cat: GeneralCategory) -> CharAction {
    use GeneralCategory::*;
    match cat {
        Control | Format | Surrogate | PrivateUse | Unassigned => CharAction::Delete, // Cc/Cf/Cs/Co/Cn
        // Lm (ModifierLetter) and Mn (NonspacingMark) fall through to Keep.
        EnclosingMark => CharAction::Delete,   // Me
        SpacingMark => CharAction::Whitespace, // Mc
        OtherNumber => CharAction::Delete,     // No
        SpaceSeparator | LineSeparator | ParagraphSeparator => CharAction::Whitespace,
        ConnectorPunctuation | DashPunctuation | OpenPunctuation | ClosePunctuation
        | InitialPunctuation | FinalPunctuation | OtherPunctuation => CharAction::Whitespace,
        MathSymbol => CharAction::Whitespace,
        CurrencySymbol | ModifierSymbol => CharAction::Delete,
        OtherSymbol => CharAction::Whitespace,
        _ => CharAction::Keep,
    }
}

fn category_replace(text: &str, cleanup: Cleanup) -> String {
    let gc = CodePointMapData::<GeneralCategory>::new();
    let mut out = String::with_capacity(text.len());
    for ch in text.chars() {
        let cat = gc.get(ch);
        let action = match cleanup {
            Cleanup::Noop => CharAction::Keep,
            Cleanup::Strong => action_strong(cat),
            Cleanup::Slug => action_slug(cat),
        };
        match action {
            CharAction::Keep => out.push(ch),
            CharAction::Delete => {}
            CharAction::Whitespace => out.push(' '),
        }
    }
    out
}

fn squash_spaces(text: &str) -> String {
    // Collapse runs of Unicode-whitespace chars into single ASCII spaces;
    // trim ends. Called inside the hot matching loop, which is why this
    // is a hand-written single-pass loop rather than a `\s+` regex
    // replace: no per-call LazyLock deref, no intermediate allocation,
    // no regex automaton overhead. `char::is_whitespace` follows the
    // Unicode `White_Space` property — covers ASCII space, tab, CR, LF,
    // NBSP (U+00A0), narrow NBSP (U+202F), ideographic space (U+3000),
    // line/paragraph separators (U+2028/U+2029). Does NOT match zero-
    // width space (U+200B) — that's Cf, not White_Space, and must be
    // removed by category_replace if unwanted.
    let mut out = String::with_capacity(text.len());
    let mut last_was_space = true; // suppresses leading whitespace
    for ch in text.chars() {
        if ch.is_whitespace() {
            if !last_was_space {
                out.push(' ');
                last_was_space = true;
            }
        } else {
            out.push(ch);
            last_was_space = false;
        }
    }
    if out.ends_with(' ') {
        out.pop();
    }
    out
}

fn casefold(text: &str) -> String {
    // ICU4X CaseMapper::fold_string — full Unicode casefold. Matches
    // Python's str.casefold() for our corpus (ß → ss, Greek sigma
    // forms normalised, etc.). Preserves the composition form of the
    // input: no implicit NFC/NFKD. If the caller wants composed output
    // they set Normalize::NFC; for decomposed they set NFKD.
    CaseMapper::new().fold_string(text).into_owned()
}

pub fn normalize(text: &str, flags: Normalize, cleanup: Cleanup) -> Option<String> {
    let mut s = if flags.contains(Normalize::STRIP) {
        text.trim().to_string()
    } else {
        text.to_string()
    };

    // Unicode normal form — at most one is meaningful; later-set wins
    // (NFKD ⊃ NFKC ⊃ NFC in "aggression").
    if flags.contains(Normalize::NFKD) {
        s = DecomposingNormalizerBorrowed::new_nfkd()
            .normalize(&s)
            .into_owned();
    } else if flags.contains(Normalize::NFKC) {
        s = ComposingNormalizerBorrowed::new_nfkc()
            .normalize(&s)
            .into_owned();
    } else if flags.contains(Normalize::NFC) {
        s = ComposingNormalizerBorrowed::new_nfc()
            .normalize(&s)
            .into_owned();
    }

    if flags.contains(Normalize::CASEFOLD) {
        s = casefold(&s);
    }

    if flags.contains(Normalize::ASCII) {
        s = ascii_text(&s);
    } else if flags.contains(Normalize::LATINIZE) {
        s = latinize_text(&s);
    }

    if cleanup != Cleanup::Noop {
        s = category_replace(&s, cleanup);
    }

    if flags.contains(Normalize::SQUASH_SPACES) {
        s = squash_spaces(&s);
    }

    if s.is_empty() { None } else { Some(s) }
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- individual flags ---

    #[test]
    fn strip_only() {
        assert_eq!(
            normalize("  hi  ", Normalize::STRIP, Cleanup::Noop),
            Some("hi".to_string())
        );
        assert_eq!(
            normalize("hi", Normalize::STRIP, Cleanup::Noop),
            Some("hi".to_string())
        );
        assert_eq!(normalize("   ", Normalize::STRIP, Cleanup::Noop), None);
        assert_eq!(normalize("", Normalize::STRIP, Cleanup::Noop), None);
    }

    #[test]
    fn casefold_basic() {
        assert_eq!(
            normalize("HELLO", Normalize::CASEFOLD, Cleanup::Noop),
            Some("hello".to_string())
        );
        assert_eq!(
            normalize("Straße", Normalize::CASEFOLD, Cleanup::Noop),
            Some("strasse".to_string())
        );
    }

    #[test]
    fn casefold_differs_from_lowercase() {
        // Python: "ß".casefold() == "ss"; "ß".lower() == "ß".
        // Our CASEFOLD matches casefold().
        assert_eq!(
            normalize("ß", Normalize::CASEFOLD, Cleanup::Noop),
            Some("ss".to_string())
        );
    }

    #[test]
    fn squash_spaces_only() {
        assert_eq!(
            normalize("a   b\t c", Normalize::SQUASH_SPACES, Cleanup::Noop),
            Some("a b c".to_string())
        );
        assert_eq!(
            normalize("  hi  ", Normalize::SQUASH_SPACES, Cleanup::Noop),
            Some("hi".to_string())
        );
    }

    // --- squash_spaces — Unicode whitespace coverage ---
    //
    // char::is_whitespace follows the Unicode White_Space property.
    // These tests pin the coverage and surface any surprises.

    fn squash(input: &str) -> Option<String> {
        normalize(input, Normalize::SQUASH_SPACES, Cleanup::Noop)
    }

    #[test]
    fn squash_ascii_whitespace() {
        // U+0020 space, U+0009 tab, U+000A LF, U+000D CR, U+000B VT, U+000C FF
        assert_eq!(squash("a\tb"), Some("a b".to_string()));
        assert_eq!(squash("a\nb"), Some("a b".to_string()));
        assert_eq!(squash("a\rb"), Some("a b".to_string()));
        assert_eq!(squash("a\u{000B}b"), Some("a b".to_string()));
        assert_eq!(squash("a\u{000C}b"), Some("a b".to_string()));
        // Mixed run
        assert_eq!(squash("a \t\r\n b"), Some("a b".to_string()));
    }

    #[test]
    fn squash_non_breaking_space() {
        // U+00A0 non-breaking space — would survive naive `trim()` on
        // whitespace-stripping implementations that only look at ASCII.
        assert_eq!(squash("a\u{00A0}b"), Some("a b".to_string()));
        assert_eq!(squash("\u{00A0}hello\u{00A0}"), Some("hello".to_string()));
    }

    #[test]
    fn squash_narrow_nbsp() {
        // U+202F narrow no-break space — used in French typography and
        // between digits in some locales.
        assert_eq!(squash("a\u{202F}b"), Some("a b".to_string()));
    }

    #[test]
    fn squash_ideographic_space() {
        // U+3000 ideographic space — the CJK full-width space.
        assert_eq!(squash("中\u{3000}文"), Some("中 文".to_string()));
    }

    #[test]
    fn squash_line_paragraph_separators() {
        // U+2028 line separator, U+2029 paragraph separator
        assert_eq!(squash("a\u{2028}b"), Some("a b".to_string()));
        assert_eq!(squash("a\u{2029}b"), Some("a b".to_string()));
    }

    #[test]
    fn squash_mixed_unicode_whitespace() {
        // Mix several kinds in one run; still collapses to one ASCII space.
        let input = "foo\u{00A0}\t\u{2003}\u{3000}bar";
        assert_eq!(squash(input), Some("foo bar".to_string()));
    }

    #[test]
    fn squash_zero_width_space_is_not_whitespace() {
        // U+200B is Cf (Format), NOT in the White_Space property.
        // It survives squash_spaces and must be removed via category_replace
        // if the caller wants it gone.
        assert_eq!(squash("a\u{200B}b"), Some("a\u{200B}b".to_string()),);
    }

    #[test]
    fn squash_only_whitespace_becomes_none() {
        // Empty after squash → None
        assert_eq!(squash("   "), None);
        assert_eq!(squash("\t\n\r"), None);
        assert_eq!(squash("\u{00A0}\u{3000}\u{2028}"), None);
    }

    #[test]
    fn squash_normalises_output_to_ascii_space() {
        // Any whitespace in the input becomes ASCII U+0020 in the output.
        let out = squash("a\u{00A0}b\u{3000}c").unwrap();
        assert_eq!(out, "a b c");
        // Confirm the output whitespace is specifically U+0020
        assert!(out.chars().filter(|c| c.is_whitespace()).all(|c| c == ' '));
    }

    #[test]
    fn nfc_recompose() {
        // "e" + U+0301 (combining acute) → "é" under NFC
        let decomposed = "e\u{0301}";
        let out = normalize(decomposed, Normalize::NFC, Cleanup::Noop).unwrap();
        assert_eq!(out, "é");
    }

    #[test]
    fn nfkd_decompose() {
        // "é" → "e" + U+0301 under NFKD
        let out = normalize("é", Normalize::NFKD, Cleanup::Noop).unwrap();
        assert_eq!(out, "e\u{0301}");
    }

    #[test]
    fn latinize_cyrillic() {
        let out = normalize("Владимир", Normalize::LATINIZE, Cleanup::Noop).unwrap();
        assert!(out.chars().all(|c| !('\u{0400}'..='\u{04FF}').contains(&c)));
    }

    #[test]
    fn ascii_cyrillic() {
        let out = normalize("Владимир", Normalize::ASCII, Cleanup::Noop).unwrap();
        assert!(out.is_ascii());
    }

    // --- cleanup variants ---

    #[test]
    fn cleanup_noop_keeps_everything() {
        assert_eq!(
            normalize("hello, world!", Normalize::empty(), Cleanup::Noop),
            Some("hello, world!".to_string())
        );
    }

    #[test]
    fn cleanup_strong_punctuation_to_whitespace() {
        // "hello,world" → "hello world" (comma → WS, then squash)
        assert_eq!(
            normalize("hello,world", Normalize::SQUASH_SPACES, Cleanup::Strong),
            Some("hello world".to_string())
        );
    }

    #[test]
    fn cleanup_strong_deletes_combining_marks() {
        // "é" (composed, U+00E9) has category Ll — kept as-is.
        // The decomposed form "e\u{0301}" hits the combining mark deletion.
        assert_eq!(
            normalize("e\u{0301}", Normalize::empty(), Cleanup::Strong),
            Some("e".to_string())
        );
    }

    #[test]
    fn cleanup_strong_empty_input_short_circuit() {
        // Pure punctuation + squash → empty → None
        assert_eq!(
            normalize("!!!", Normalize::SQUASH_SPACES, Cleanup::Strong),
            None
        );
    }

    #[test]
    fn cleanup_slug_keeps_nonspacing_marks() {
        // Unlike Strong, Slug preserves combining marks.
        let out = normalize("e\u{0301}", Normalize::empty(), Cleanup::Slug).unwrap();
        assert_eq!(out, "e\u{0301}");
    }

    #[test]
    fn cleanup_slug_deletes_controls() {
        // Unlike Strong (which would replace with WS), Slug deletes Cc.
        let out = normalize("a\u{0007}b", Normalize::empty(), Cleanup::Slug).unwrap();
        assert_eq!(out, "ab");
    }

    // --- composed pipelines (match legacy normalizers) ---

    #[test]
    fn parity_normalize_display() {
        // normalize_display(text) == squash_spaces(text)
        // With STRIP | SQUASH_SPACES and Noop:
        assert_eq!(
            normalize(
                "  Foo  Bar  ",
                Normalize::STRIP | Normalize::SQUASH_SPACES,
                Cleanup::Noop,
            ),
            Some("Foo Bar".to_string())
        );
    }

    #[test]
    fn parity_normalize_compare() {
        // _normalize_compare(text) == squash_spaces(text).casefold()
        let out = normalize(
            "  FOO   Bar  ",
            Normalize::STRIP | Normalize::CASEFOLD | Normalize::SQUASH_SPACES,
            Cleanup::Noop,
        );
        assert_eq!(out, Some("foo bar".to_string()));
    }

    #[test]
    fn parity_normalize_text_stopwords() {
        // Old normalize_text: casefold → category_replace(SLUG) → squash
        let out = normalize(
            "Hello, World!",
            Normalize::CASEFOLD | Normalize::SQUASH_SPACES,
            Cleanup::Slug,
        );
        assert_eq!(out, Some("hello world".to_string()));
    }

    // --- empty result ---

    #[test]
    fn empty_result_returns_none() {
        assert_eq!(
            normalize(
                "",
                Normalize::CASEFOLD | Normalize::SQUASH_SPACES,
                Cleanup::Noop
            ),
            None
        );
        assert_eq!(
            normalize("   ", Normalize::SQUASH_SPACES, Cleanup::Noop),
            None
        );
    }
}
