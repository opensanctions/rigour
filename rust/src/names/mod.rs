// Mirrors the `rigour.names.*` Python submodule layout — name parsing,
// tagging, and the various Replacer/Scanner dictionaries.

#[cfg(feature = "python")]
pub mod analyze;
pub mod matcher;
#[cfg(feature = "python")]
pub mod name;
pub mod org_types;
#[cfg(feature = "python")]
pub mod part;
pub mod person_names;
pub mod pick;
pub mod prefix;
pub mod stopwords;
pub mod symbol;
pub mod symbols;
pub mod tag;
pub mod tagger;
