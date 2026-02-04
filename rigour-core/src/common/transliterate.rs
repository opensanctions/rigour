/// Text transliteration utilities.
///
/// Provides functions to transliterate text to ASCII using ICU.
/// This matches the behavior of Python's normality library.

use std::cell::RefCell;
use rust_icu_utrans as utrans;

thread_local! {
    /// ICU transliterator for ASCII conversion.
    /// Uses the same script as Python's normality library:
    /// "Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Accents-Any; [:Symbol:] Remove; [:Nonspacing Mark:] Remove; Latin-ASCII"
    static ASCII_TRANSLITERATOR: RefCell<Option<utrans::UTransliterator>> = RefCell::new(None);
}

const ASCII_SCRIPT: &str = "Any-Latin; NFKD; [:Nonspacing Mark:] Remove; Accents-Any; [:Symbol:] Remove; [:Nonspacing Mark:] Remove; Latin-ASCII";

/// Transliterate text to ASCII.
///
/// This function converts text from any script to ASCII using ICU.
/// It matches the behavior of Python's normality.ascii_text().
///
/// # Arguments
/// * `text` - The text to transliterate
///
/// # Returns
/// ASCII-only string
///
/// # Examples
/// ```
/// use rigour_core::common::ascii_text;
///
/// assert_eq!(ascii_text("Café"), "Cafe");
/// assert_eq!(ascii_text("АМУРСКАЯ"), "AMURSKAA");
/// ```
pub fn ascii_text(text: &str) -> String {
    // Fast path: if already ASCII, return as-is
    if text.is_ascii() {
        return text.to_string();
    }

    // Transliterate using ICU
    ASCII_TRANSLITERATOR.with(|trans_cell| {
        let mut trans = trans_cell.borrow_mut();
        if trans.is_none() {
            *trans = Some(
                utrans::UTransliterator::new(
                    ASCII_SCRIPT,
                    None,  // No custom rules
                    rust_icu_sys::UTransDirection::UTRANS_FORWARD,
                )
                .expect("Failed to create ASCII transliterator"),
            );
        }

        let transliterator = trans.as_ref().unwrap();
        match transliterator.transliterate(text) {
            Ok(result) => result,
            Err(_) => {
                // Fallback: if ICU fails, return original text
                // filtered to ASCII (replacing non-ASCII with '?')
                text.chars()
                    .map(|c| if c.is_ascii() { c } else { '?' })
                    .collect()
            }
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ascii_text_already_ascii() {
        assert_eq!(ascii_text("hello world"), "hello world");
        assert_eq!(ascii_text("123"), "123");
    }

    #[test]
    fn test_ascii_text_cyrillic() {
        // Test Cyrillic transliteration - should match normality's ICU behavior
        let result = ascii_text("АМУРСКАЯ");
        assert_eq!(result, "AMURSKAA", "Cyrillic should transliterate to AMURSKAA");
        assert!(result.is_ascii(), "Result should be ASCII: {}", result);
    }

    #[test]
    fn test_ascii_text_accents() {
        assert_eq!(ascii_text("Café"), "Cafe");
        assert_eq!(ascii_text("naïve"), "naive");
    }

    #[test]
    fn test_ascii_text_mixed() {
        let result = ascii_text("Д.127");
        assert!(result.is_ascii());
        assert!(result.contains("127"));
    }

    #[test]
    fn test_ascii_text_result_is_ascii() {
        // Property: result should always be ASCII
        let inputs = vec![
            "Café",
            "Москва",
            "مرحبا",
            "Здравствуйте",
        ];

        for input in inputs {
            let result = ascii_text(input);
            assert!(
                result.is_ascii(),
                "ascii_text({}) produced non-ASCII: {}",
                input,
                result
            );
        }
    }

    #[test]
    fn test_thread_safety() {
        // Test that thread-local pattern works correctly with multiple threads
        use std::thread;

        let handles: Vec<_> = (0..10)
            .map(|i| {
                thread::spawn(move || {
                    // Each thread gets its own transliterator
                    let text = format!("Test {} Café Москва", i);
                    let result = ascii_text(&text);
                    assert!(result.is_ascii());
                    assert!(result.contains(&i.to_string()));
                    result
                })
            })
            .collect();

        // All threads should complete successfully
        for handle in handles {
            let result = handle.join().unwrap();
            assert!(result.is_ascii());
        }
        // Thread-local UTransliterators are dropped when threads exit
    }

    #[test]
    fn test_transliterator_reuse() {
        // Test that the same thread reuses the transliterator
        let result1 = ascii_text("Café");
        let result2 = ascii_text("Naïve");
        let result3 = ascii_text("Москва");

        assert_eq!(result1, "Cafe");
        assert_eq!(result2, "Naive");
        assert!(result3.is_ascii());
        // All three calls use the same thread-local transliterator
    }
}
