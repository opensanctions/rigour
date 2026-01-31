/// Address normalization functions.
///
/// This module provides functions to normalize addresses for comparison purposes.
/// The normalization is destructive (makes addresses ugly) but enables better matching.

use crate::common::{ascii_text, get_category_action, is_address_allowed_char, CategoryAction, WS};

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
}
