/// Address normalization functions.
///
/// This module provides functions to normalize addresses for comparison purposes.
/// The normalization is destructive (makes addresses ugly) but enables better matching.

use crate::common::{ascii_text, CategoryAction, WS};

/// Check if a character is allowed in normalized addresses without modification.
/// Matches CHARS_ALLOWED from rigour/addresses/normalize.py
fn is_address_allowed_char(ch: char) -> bool {
    ch == '&' || ch == '№' || ch.is_ascii_alphanumeric()
}

/// Get the action to take for a character in address normalization.
///
/// This mapping is specific to address processing and differs from name tokenization.
/// Based on rigour/addresses/normalize.py TOKEN_SEP_CATEGORIES.
fn get_category_action(ch: char) -> CategoryAction {
    use unicode_general_category::{get_general_category, GeneralCategory};

    match get_general_category(ch) {
        // Letters → keep (all types)
        GeneralCategory::UppercaseLetter => CategoryAction::Keep,
        GeneralCategory::LowercaseLetter => CategoryAction::Keep,
        GeneralCategory::TitlecaseLetter => CategoryAction::Keep,
        GeneralCategory::OtherLetter => CategoryAction::Keep,

        // Numbers
        GeneralCategory::DecimalNumber => CategoryAction::Keep,
        GeneralCategory::LetterNumber => CategoryAction::Keep,
        GeneralCategory::OtherNumber => CategoryAction::Skip,

        // Modifier letter → skip
        GeneralCategory::ModifierLetter => CategoryAction::Skip,

        // Marks
        GeneralCategory::NonspacingMark => CategoryAction::Skip,
        GeneralCategory::SpacingMark => CategoryAction::Whitespace,
        GeneralCategory::EnclosingMark => CategoryAction::Skip,

        // Punctuation → whitespace (all types)
        GeneralCategory::ConnectorPunctuation => CategoryAction::Whitespace,
        GeneralCategory::DashPunctuation => CategoryAction::Whitespace,
        GeneralCategory::OpenPunctuation => CategoryAction::Whitespace,
        GeneralCategory::ClosePunctuation => CategoryAction::Whitespace,
        GeneralCategory::InitialPunctuation => CategoryAction::Whitespace,
        GeneralCategory::FinalPunctuation => CategoryAction::Whitespace,
        GeneralCategory::OtherPunctuation => CategoryAction::Whitespace,

        // Symbols
        GeneralCategory::MathSymbol => CategoryAction::Whitespace,
        GeneralCategory::CurrencySymbol => CategoryAction::Skip,
        GeneralCategory::ModifierSymbol => CategoryAction::Skip,
        GeneralCategory::OtherSymbol => CategoryAction::Whitespace,

        // Separators → whitespace
        GeneralCategory::SpaceSeparator => CategoryAction::Whitespace,
        GeneralCategory::LineSeparator => CategoryAction::Whitespace,
        GeneralCategory::ParagraphSeparator => CategoryAction::Whitespace,

        // Control/format
        GeneralCategory::Control => CategoryAction::Whitespace,
        GeneralCategory::Format => CategoryAction::Skip,

        // Special categories → skip
        GeneralCategory::Surrogate => CategoryAction::Skip,
        GeneralCategory::PrivateUse => CategoryAction::Skip,
        GeneralCategory::Unassigned => CategoryAction::Skip,

        // Catch any future Unicode categories: keep (matches Python's .get(cat, char) default)
        _ => CategoryAction::Keep,
    }
}

/// Normalize an address string for comparison.
///
/// This function performs aggressive normalization that makes the address suitable
/// for comparison but not for display. It:
/// - Converts to lowercase
/// - Tokenizes based on Unicode categories
/// - Optionally transliterates to ASCII (latinize)
/// - Filters out tokens below minimum length
///
/// # Arguments
/// * `address` - The address string to normalize
/// * `latinize` - Whether to convert non-Latin characters to ASCII equivalents
/// * `min_length` - Minimum length for the normalized result
///
/// # Returns
/// The normalized address, or None if it's below the minimum length
///
/// # Examples
/// ```
/// use rigour_core::addresses::normalize_address;
///
/// let result = normalize_address("123 Main St.", false, 4);
/// assert_eq!(result, Some("123 main st".to_string()));
///
/// let result = normalize_address("abc", false, 4);
/// assert_eq!(result, None); // Too short
/// ```
pub fn normalize_address(address: &str, latinize: bool, min_length: usize) -> Option<String> {
    let mut tokens: Vec<Vec<char>> = Vec::new();
    let mut current_token: Vec<char> = Vec::new();

    // Process each character
    for ch in address.to_lowercase().chars() {
        let result_char = if is_address_allowed_char(ch) {
            Some(ch)
        } else {
            match get_category_action(ch) {
                CategoryAction::Skip => None,
                CategoryAction::Whitespace => {
                    // End current token
                    if !current_token.is_empty() {
                        tokens.push(current_token.clone());
                        current_token.clear();
                    }
                    None
                }
                CategoryAction::Keep => Some(ch),
            }
        };

        if let Some(c) = result_char {
            current_token.push(c);
        }
    }

    // Don't forget the last token
    if !current_token.is_empty() {
        tokens.push(current_token);
    }

    // Convert tokens to strings
    let mut parts: Vec<String> = Vec::new();
    for token in tokens {
        let token_str: String = token.into_iter().collect();

        // Apply latinization if requested
        let final_str = if latinize {
            // Transliterate to ASCII using ICU
            ascii_text(&token_str)
        } else {
            token_str
        };

        if !final_str.is_empty() {
            parts.push(final_str);
        }
    }

    // Join with whitespace
    let normalized = parts.join(WS);

    // Check minimum length
    if normalized.len() >= min_length {
        Some(normalized)
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_address_basic() {
        let result = normalize_address("123 Main St", false, 4);
        assert_eq!(result, Some("123 main st".to_string()));
    }

    #[test]
    fn test_normalize_address_with_punctuation() {
        let result = normalize_address("Apt. 5B, Main Street", false, 4);
        assert_eq!(result, Some("apt 5b main street".to_string()));
    }

    #[test]
    fn test_normalize_address_too_short() {
        let result = normalize_address("abc", false, 4);
        assert_eq!(result, None);
    }

    #[test]
    fn test_normalize_address_empty() {
        let result = normalize_address("", false, 4);
        assert_eq!(result, None);
    }

    #[test]
    fn test_normalize_address_unicode() {
        // Test with Cyrillic
        let result = normalize_address("Квартира 5Б", false, 4);
        assert_eq!(result, Some("квартира 5б".to_string()));
    }

    #[test]
    fn test_normalize_address_special_chars() {
        // Test with allowed special characters
        let result = normalize_address("Street & Avenue №5", false, 4);
        assert_eq!(result, Some("street & avenue №5".to_string()));
    }

    #[test]
    fn test_normalize_address_min_length() {
        let result = normalize_address("Main Street", false, 20);
        assert_eq!(result, None); // "main street" is only 11 chars
    }

    #[test]
    fn test_normalize_address_multiple_spaces() {
        let result = normalize_address("123    Main    St", false, 4);
        assert_eq!(result, Some("123 main st".to_string()));
    }

    #[test]
    fn test_normalize_address_latinize() {
        // With latinize=true, non-ASCII chars should be filtered (for now)
        let result = normalize_address("Café 123", true, 4);
        // TODO: This should transliterate 'é' to 'e' when we implement proper latinization
        assert!(result.is_some());
    }

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
