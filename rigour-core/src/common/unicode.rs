/// Shared Unicode category handling types.
///
/// This module provides common type definitions used by both address and name
/// processing modules for Unicode character categorization.

/// Action to take for a Unicode character during text processing.
///
/// This enum is used by both address normalization and name tokenization,
/// though each module defines its own mapping from Unicode categories to actions.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CategoryAction {
    /// Remove the character entirely
    Skip,
    /// Replace with whitespace (token separator)
    Whitespace,
    /// Keep the character as-is
    Keep,
}
