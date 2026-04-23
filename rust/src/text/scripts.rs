// Unicode script detection via ICU4X. Two exports:
//
// - `codepoint_script` — faithful Unicode Script property lookup for a single
//   codepoint. Returns "Common", "Inherited", real script long names, or None
//   for unassigned/invalid codepoints. (Takes u32 not char so callers can pass
//   ord() of any value including surrogates without triggering a TypeError at
//   the FFI boundary.)
//
// - `text_scripts` — set of distinct "real" scripts present in a string.
//   Iterates chars, keeps only those with General_Category in L* (letter) or
//   N* (number) groups, excludes Common/Inherited/Unknown from the result.
//   Foundational for the script-predicate family in rigour.text.scripts
//   (is_latin, is_modern_alphabet, can_latinize, is_dense_script).

use icu::properties::{
    CodePointMapData,
    props::{GeneralCategory, GeneralCategoryGroup, NamedEnumeratedProperty, Script},
};

pub fn codepoint_script(cp: u32) -> Option<&'static str> {
    let script = CodePointMapData::<Script>::new().get32(cp);
    if script == Script::Unknown {
        return None;
    }
    Some(script.long_name())
}

pub fn text_scripts(text: &str) -> Vec<&'static str> {
    let script_map = CodePointMapData::<Script>::new();
    let gc_map = CodePointMapData::<GeneralCategory>::new();
    let mut scripts: Vec<&'static str> = Vec::new();
    for ch in text.chars() {
        let gc = gc_map.get(ch);
        if !GeneralCategoryGroup::Letter.contains(gc) && !GeneralCategoryGroup::Number.contains(gc)
        {
            continue;
        }
        let script = script_map.get(ch);
        if matches!(script, Script::Common | Script::Inherited | Script::Unknown) {
            continue;
        }
        let name = script.long_name();
        if !scripts.contains(&name) {
            scripts.push(name);
        }
    }
    scripts
}

/// Return the scripts both strings have in common. Equivalent to
/// `text_scripts(a) ∩ text_scripts(b)` — only real scripts from
/// Letter/Number codepoints; Common/Inherited/Unknown are never
/// returned. Order: first-appearance in `a`.
///
/// An empty result is ambiguous — it can mean "scripts are
/// disjoint" *or* "one side has no real scripts" (numeric-only,
/// punctuation-only, empty). Pruning callers that care about the
/// distinction should treat empty-script inputs as wildcards.
pub fn common_scripts(a: &str, b: &str) -> Vec<&'static str> {
    let b_scripts: std::collections::HashSet<&'static str> = text_scripts(b).into_iter().collect();
    text_scripts(a)
        .into_iter()
        .filter(|s| b_scripts.contains(s))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codepoint_script_latin_ascii() {
        assert_eq!(codepoint_script(0x0041), Some("Latin")); // A
        assert_eq!(codepoint_script(0x0061), Some("Latin")); // a
    }

    #[test]
    fn codepoint_script_common_inherited() {
        assert_eq!(codepoint_script(0x0020), Some("Common")); // space
        assert_eq!(codepoint_script(0x0030), Some("Common")); // digit 0
        assert_eq!(codepoint_script(0x0301), Some("Inherited")); // combining acute
    }

    #[test]
    fn codepoint_script_non_latin_scripts() {
        assert_eq!(codepoint_script(0x0410), Some("Cyrillic")); // А
        assert_eq!(codepoint_script(0x4E2D), Some("Han")); // 中
        assert_eq!(codepoint_script(0xAC00), Some("Hangul")); // 가
        assert_eq!(codepoint_script(0x0391), Some("Greek")); // Α
        assert_eq!(codepoint_script(0x0627), Some("Arabic")); // ا
        assert_eq!(codepoint_script(0x0531), Some("Armenian")); // Ա
        assert_eq!(codepoint_script(0x10A0), Some("Georgian")); // Ⴀ
    }

    #[test]
    fn codepoint_script_surrogate_and_invalid() {
        assert_eq!(codepoint_script(0xD800), None); // lone surrogate
        assert_eq!(codepoint_script(0x10FFFE), None); // unassigned noncharacter
    }

    #[test]
    fn text_scripts_mixed_string() {
        let scripts = text_scripts("Hello, мир! 中文 123");
        assert_eq!(scripts.len(), 3);
        assert!(scripts.contains(&"Latin"));
        assert!(scripts.contains(&"Cyrillic"));
        assert!(scripts.contains(&"Han"));
    }

    #[test]
    fn text_scripts_filters_common() {
        // digits, punctuation, space all have Script::Common → excluded
        assert!(text_scripts("123 !@#").is_empty());
        assert!(text_scripts("").is_empty());
    }

    #[test]
    fn text_scripts_single_script_inputs() {
        assert_eq!(text_scripts("Hello"), vec!["Latin"]);
        assert_eq!(text_scripts("Привет"), vec!["Cyrillic"]);
        assert_eq!(text_scripts("你好"), vec!["Han"]);
    }

    #[test]
    fn text_scripts_dedups() {
        // single input with repeated script
        let scripts = text_scripts("abcabc");
        assert_eq!(scripts, vec!["Latin"]);
    }

    // --- common_scripts ---

    #[test]
    fn common_scripts_both_latin() {
        assert_eq!(common_scripts("Hello", "World"), vec!["Latin"]);
    }

    #[test]
    fn common_scripts_disjoint_latin_han() {
        assert!(common_scripts("Hello", "你好").is_empty());
        assert!(common_scripts("你好", "Hello").is_empty());
    }

    #[test]
    fn common_scripts_mixed_both_sides() {
        // Both sides contain Latin + Han; both survive intersection.
        let out = common_scripts("Hello 你好", "Tokyo 東京");
        assert_eq!(out.len(), 2);
        assert!(out.contains(&"Latin"));
        assert!(out.contains(&"Han"));
    }

    #[test]
    fn common_scripts_partial_overlap() {
        // a has Latin + Cyrillic, b has Cyrillic only.
        assert_eq!(common_scripts("Hello мир", "Владимир"), vec!["Cyrillic"]);
    }

    #[test]
    fn common_scripts_numbers_only() {
        // Both are Common-only → both text_scripts return empty → empty.
        assert!(common_scripts("007", "123").is_empty());
    }

    #[test]
    fn common_scripts_punctuation_only() {
        assert!(common_scripts("!@#", "...").is_empty());
    }

    #[test]
    fn common_scripts_numbers_vs_latin() {
        // One side is pure Common — no real scripts to intersect.
        assert!(common_scripts("007", "Hello").is_empty());
        assert!(common_scripts("Hello", "007").is_empty());
    }

    #[test]
    fn common_scripts_empty_inputs() {
        assert!(common_scripts("", "").is_empty());
        assert!(common_scripts("", "Hello").is_empty());
        assert!(common_scripts("Hello", "").is_empty());
    }

    #[test]
    fn common_scripts_never_returns_pseudo_scripts() {
        // Even when both strings are loaded with Common/Inherited
        // codepoints, neither is a valid return value.
        let out = common_scripts("2024 !@# 1-2", "!!! ... ???");
        assert!(out.is_empty());
        assert!(!out.contains(&"Common"));
        assert!(!out.contains(&"Inherited"));
    }
}
