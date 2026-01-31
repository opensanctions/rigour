/// Unicode category handling utilities.
///
/// This module provides functions to categorize Unicode characters in a way
/// that matches Python's unicodedata.category() behavior.

use std::collections::HashMap;
use once_cell::sync::Lazy;

/// Unicode category actions: None (skip), WS (whitespace), or keep the character
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CategoryAction {
    Skip,      // Remove the character
    Whitespace, // Replace with whitespace
    Keep,      // Keep the character as-is
}

/// Mapping of Unicode general categories to their actions for tokenization.
/// This matches the behavior from rigour/addresses/normalize.py
static TOKEN_SEP_CATEGORIES: Lazy<HashMap<&'static str, CategoryAction>> = Lazy::new(|| {
    let mut map = HashMap::new();

    // Control characters -> whitespace
    map.insert("Cc", CategoryAction::Whitespace);

    // Format characters -> skip
    map.insert("Cf", CategoryAction::Skip);

    // Private use, unassigned -> skip
    map.insert("Co", CategoryAction::Skip);
    map.insert("Cn", CategoryAction::Skip);

    // Letter modifiers, marks -> whitespace or skip
    map.insert("Lm", CategoryAction::Skip);
    map.insert("Mn", CategoryAction::Skip);
    map.insert("Mc", CategoryAction::Whitespace);
    map.insert("Me", CategoryAction::Skip);

    // Numbers (other) -> skip
    map.insert("No", CategoryAction::Skip);

    // Separators -> whitespace
    map.insert("Zs", CategoryAction::Whitespace);
    map.insert("Zl", CategoryAction::Whitespace);
    map.insert("Zp", CategoryAction::Whitespace);

    // Punctuation -> whitespace
    map.insert("Pc", CategoryAction::Whitespace);
    map.insert("Pd", CategoryAction::Whitespace);
    map.insert("Ps", CategoryAction::Whitespace);
    map.insert("Pe", CategoryAction::Whitespace);
    map.insert("Pi", CategoryAction::Whitespace);
    map.insert("Pf", CategoryAction::Whitespace);
    map.insert("Po", CategoryAction::Whitespace);

    // Symbols (math, currency, modifier) -> whitespace or skip
    map.insert("Sm", CategoryAction::Whitespace);
    map.insert("Sc", CategoryAction::Skip);
    map.insert("Sk", CategoryAction::Skip);
    map.insert("So", CategoryAction::Whitespace);

    map
});

/// Get the Unicode general category for a character.
/// Returns a two-letter category code (e.g., "Lu", "Nd", "Po").
pub fn get_category(ch: char) -> String {
    use unicode_normalization::char::is_combining_mark;

    // Map Rust's char category to Unicode general category codes
    if ch.is_alphabetic() {
        if ch.is_uppercase() {
            "Lu".to_string()
        } else if ch.is_lowercase() {
            "Ll".to_string()
        } else {
            "Lo".to_string() // Other letters
        }
    } else if ch.is_numeric() {
        if ch.is_ascii_digit() {
            "Nd".to_string() // Decimal number
        } else {
            "No".to_string() // Other number
        }
    } else if ch.is_whitespace() {
        "Zs".to_string() // Space separator
    } else if ch.is_control() {
        "Cc".to_string() // Control character
    } else if is_combining_mark(ch) {
        "Mn".to_string() // Non-spacing mark
    } else if ch.is_ascii_punctuation() {
        "Po".to_string() // Other punctuation
    } else {
        "So".to_string() // Other symbol (fallback)
    }
}

/// Get the action to take for a character based on its Unicode category.
pub fn get_category_action(ch: char) -> CategoryAction {
    let category = get_category(ch);
    TOKEN_SEP_CATEGORIES
        .get(category.as_str())
        .copied()
        .unwrap_or(CategoryAction::Keep)
}

/// Check if a character is allowed in normalized addresses without modification.
/// Matches CHARS_ALLOWED from rigour/addresses/normalize.py
pub fn is_address_allowed_char(ch: char) -> bool {
    ch == '&' || ch == '№' || ch.is_ascii_alphanumeric()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_category_actions() {
        // Whitespace
        assert_eq!(get_category_action(' '), CategoryAction::Whitespace);
        assert_eq!(get_category_action('\t'), CategoryAction::Whitespace);

        // ASCII alphanumeric should be kept
        assert_eq!(get_category_action('a'), CategoryAction::Keep);
        assert_eq!(get_category_action('Z'), CategoryAction::Keep);
        assert_eq!(get_category_action('5'), CategoryAction::Keep);

        // Punctuation -> whitespace
        assert_eq!(get_category_action('.'), CategoryAction::Whitespace);
        assert_eq!(get_category_action(','), CategoryAction::Whitespace);
    }

    #[test]
    fn test_address_allowed_chars() {
        // Allowed chars
        assert!(is_address_allowed_char('a'));
        assert!(is_address_allowed_char('Z'));
        assert!(is_address_allowed_char('5'));
        assert!(is_address_allowed_char('&'));
        assert!(is_address_allowed_char('№'));

        // Not allowed
        assert!(!is_address_allowed_char(' '));
        assert!(!is_address_allowed_char('.'));
        assert!(!is_address_allowed_char('!'));
    }
}
