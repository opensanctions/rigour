/// Name tokenization and normalization functions.
///
/// This module provides functions to split person and entity names into parts,
/// and normalize them for comparison and matching.

use crate::common::CategoryAction;

const SKIP_CHARACTERS: &[char] = &['.', '\u{2019}', '\''];  // period, right single quote, apostrophe

/// Get the action for a Unicode category in name tokenization.
///
/// This mapping is specific to name processing and differs from address
/// normalization. Based on rigour/names/tokenize.py TOKEN_SEP_CATEGORIES.
///
/// # Arguments
/// * `ch` - The character to classify
///
/// # Returns
/// The action to take for this character
fn get_name_category_action(ch: char) -> CategoryAction {
    use unicode_general_category::{get_general_category, GeneralCategory};

    match get_general_category(ch) {
        // Letters → keep
        GeneralCategory::UppercaseLetter => CategoryAction::Keep,
        GeneralCategory::LowercaseLetter => CategoryAction::Keep,
        GeneralCategory::TitlecaseLetter => CategoryAction::Keep,
        GeneralCategory::OtherLetter => CategoryAction::Keep,

        // Decimal numbers → keep
        GeneralCategory::DecimalNumber => CategoryAction::Keep,
        GeneralCategory::LetterNumber => CategoryAction::Keep,

        // Modifier letter → skip
        GeneralCategory::ModifierLetter => CategoryAction::Skip,

        // Marks
        GeneralCategory::NonspacingMark => CategoryAction::Skip,
        GeneralCategory::SpacingMark => CategoryAction::Whitespace,
        GeneralCategory::EnclosingMark => CategoryAction::Skip,

        // Other number → skip
        GeneralCategory::OtherNumber => CategoryAction::Skip,

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

/// Split a person or entity's name into name parts.
///
/// This function tokenizes a name by Unicode category, removing certain
/// characters and using others as token separators.
///
/// # Arguments
/// * `text` - The name string to tokenize
/// * `token_min_length` - Minimum length for tokens (default: 1)
///
/// # Returns
/// Vector of name part strings
///
/// # Examples
/// ```
/// use rigour_core::names::tokenize_name;
///
/// let tokens = tokenize_name("John Smith", 1);
/// assert_eq!(tokens, vec!["John", "Smith"]);
///
/// let tokens = tokenize_name("O'Brien", 1);
/// assert_eq!(tokens, vec!["OBrien"]);
///
/// let tokens = tokenize_name("Müller & Co.", 1);
/// assert_eq!(tokens, vec!["Müller", "Co"]);
/// ```
pub fn tokenize_name(text: &str, token_min_length: usize) -> Vec<String> {
    let mut tokens: Vec<String> = Vec::new();
    let mut token: Vec<char> = Vec::new();

    for ch in text.chars() {
        // Skip certain characters (apostrophes, periods)
        if SKIP_CHARACTERS.contains(&ch) {
            continue;
        }

        let action = get_name_category_action(ch);

        match action {
            CategoryAction::Skip => {
                // Skip this character
                continue;
            }
            CategoryAction::Whitespace => {
                // End current token
                if token.len() >= token_min_length {
                    tokens.push(token.iter().collect());
                }
                token.clear();
            }
            CategoryAction::Keep => {
                // Add to current token
                token.push(ch);
            }
        }
    }

    // Push final token if any
    if token.len() >= token_min_length {
        tokens.push(token.iter().collect());
    }

    tokens
}

/// Prepare a name for tokenization and matching.
///
/// Applies Unicode case folding for caseless comparison.
///
/// # Arguments
/// * `name` - The name string to prenormalize
///
/// # Returns
/// Casefolded name string
///
/// # Examples
/// ```
/// use rigour_core::names::prenormalize_name;
///
/// assert_eq!(prenormalize_name("John SMITH"), "john smith");
/// assert_eq!(prenormalize_name(""), "");
/// ```
pub fn prenormalize_name(name: &str) -> String {
    // Use full Unicode case folding to match Python's str.casefold()
    // The unicode-casefold crate provides proper case folding (e.g., ß → ss)
    use unicode_casefold::UnicodeCaseFold;

    name.chars()
        .case_fold()
        .collect()
}

/// Normalize a name for tokenization and matching.
///
/// This function:
/// 1. Prenormalizes (casefolds) the name
/// 2. Tokenizes it
/// 3. Joins tokens with separator
/// 4. Returns None if result is empty
///
/// # Arguments
/// * `name` - The name string to normalize
/// * `sep` - Token separator (default: " ")
///
/// # Returns
/// Normalized name string, or None if empty
///
/// # Examples
/// ```
/// use rigour_core::names::normalize_name;
///
/// assert_eq!(normalize_name("John SMITH", " "), Some("john smith".to_string()));
/// assert_eq!(normalize_name("O'Brien", " "), Some("obrien".to_string()));
/// assert_eq!(normalize_name("   ", " "), None);
/// assert_eq!(normalize_name("", " "), None);
/// ```
pub fn normalize_name(name: &str, sep: &str) -> Option<String> {
    if name.is_empty() {
        return None;
    }

    let prenormalized = prenormalize_name(name);
    let tokens = tokenize_name(&prenormalized, 1);

    if tokens.is_empty() {
        return None;
    }

    let joined = tokens.join(sep);
    if joined.is_empty() {
        None
    } else {
        Some(joined)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tokenize_name_simple() {
        let tokens = tokenize_name("John Smith", 1);
        assert_eq!(tokens, vec!["John", "Smith"]);
    }

    #[test]
    fn test_tokenize_name_apostrophe() {
        // Apostrophes should be skipped
        let tokens = tokenize_name("O'Brien", 1);
        assert_eq!(tokens, vec!["OBrien"]);

        let tokens = tokenize_name("d'Artagnan", 1);
        assert_eq!(tokens, vec!["dArtagnan"]);
    }

    #[test]
    fn test_tokenize_name_punctuation() {
        // Punctuation becomes whitespace
        let tokens = tokenize_name("Müller & Co.", 1);
        assert_eq!(tokens, vec!["Müller", "Co"]);

        let tokens = tokenize_name("Smith-Jones", 1);
        assert_eq!(tokens, vec!["Smith", "Jones"]);
    }

    #[test]
    fn test_tokenize_name_unicode() {
        let tokens = tokenize_name("Владимир Путин", 1);
        assert_eq!(tokens, vec!["Владимир", "Путин"]);
    }

    #[test]
    fn test_tokenize_name_min_length() {
        let tokens = tokenize_name("A B CD EFG", 2);
        assert_eq!(tokens, vec!["CD", "EFG"]);

        let tokens = tokenize_name("A B CD EFG", 3);
        assert_eq!(tokens, vec!["EFG"]);
    }

    #[test]
    fn test_prenormalize_name() {
        assert_eq!(prenormalize_name("John SMITH"), "john smith");
        assert_eq!(prenormalize_name("MÜLLER"), "müller");
        assert_eq!(prenormalize_name("O'Brien"), "o'brien");
        assert_eq!(prenormalize_name(""), "");
    }

    #[test]
    fn test_normalize_name() {
        assert_eq!(
            normalize_name("John SMITH", " "),
            Some("john smith".to_string())
        );
        assert_eq!(
            normalize_name("O'Brien", " "),
            Some("obrien".to_string())
        );
        assert_eq!(
            normalize_name("Müller & Co.", " "),
            Some("müller co".to_string())
        );
    }

    #[test]
    fn test_normalize_name_empty() {
        assert_eq!(normalize_name("", " "), None);
        assert_eq!(normalize_name("   ", " "), None);
        assert_eq!(normalize_name("...", " "), None);
    }

    #[test]
    fn test_normalize_name_custom_sep() {
        assert_eq!(
            normalize_name("John Smith", "-"),
            Some("john-smith".to_string())
        );
        assert_eq!(
            normalize_name("John Smith", ""),
            Some("johnsmith".to_string())
        );
    }

    #[test]
    fn test_normalize_name_cyrillic() {
        assert_eq!(
            normalize_name("Владимир ПУТИН", " "),
            Some("владимир путин".to_string())
        );
    }
}
