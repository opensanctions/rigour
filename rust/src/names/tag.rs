//! Tag enums for classifying names and name parts.
//!
//! - [`NameTypeTag`] — what kind of thing a name describes
//!   (person / organisation / object / unknown).
//! - [`NamePartTag`] — the structural role of a part within a name
//!   (given / family / middle / honorific / stopword / …).
//!
//! Both are exposed to Python as `#[pyclass]` enums. Hashing and
//! equality are structural.

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// What kind of thing a name describes.
///
/// Drives which pipeline passes apply when a [`crate::names::name::Name`]
/// is analysed:
/// * `PER` → person-prefix strip + person tagger
/// * `ORG` / `ENT` → org-type replacement + org-prefix strip + org tagger
/// * `OBJ` / `UNK` → construction only, no tagging
#[allow(non_camel_case_types)]
#[cfg_attr(
    feature = "python",
    pyclass(eq, hash, frozen, from_py_object, module = "rigour._core")
)]
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash)]
pub enum NameTypeTag {
    UNK,
    ENT,
    PER,
    ORG,
    OBJ,
}

impl NameTypeTag {
    /// Short stable string key used for downstream serialisation
    /// (index fields, logs, JSON output). Matches the variant name.
    pub fn value(&self) -> &'static str {
        match self {
            NameTypeTag::UNK => "UNK",
            NameTypeTag::ENT => "ENT",
            NameTypeTag::PER => "PER",
            NameTypeTag::ORG => "ORG",
            NameTypeTag::OBJ => "OBJ",
        }
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl NameTypeTag {
    #[getter(value)]
    fn py_value(&self) -> &'static str {
        self.value()
    }
}

/// The structural role of a part within a name.
///
/// A newly-constructed [`crate::names::part::NamePart`] starts as
/// `UNSET`; the tagging pipeline promotes it to one of the concrete
/// variants based on surrounding context, external hints (firstName,
/// lastName, …), or pattern matches (numeric, stopword, legal form).
#[allow(non_camel_case_types)]
#[cfg_attr(
    feature = "python",
    pyclass(eq, hash, frozen, from_py_object, module = "rigour._core")
)]
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash)]
pub enum NamePartTag {
    UNSET,
    AMBIGUOUS,

    TITLE,
    GIVEN,
    MIDDLE,
    FAMILY,
    TRIBAL,
    PATRONYMIC,
    MATRONYMIC,
    HONORIFIC,
    SUFFIX,
    NICK,

    STOP,
    NUM,
    LEGAL,
}

/// Tags that match anything under [`NamePartTag::can_match`] —
/// neutral placeholders (`UNSET`, `AMBIGUOUS`) and stopwords
/// (semantically carry no name-side information).
pub const WILDCARDS: &[NamePartTag] = &[
    NamePartTag::UNSET,
    NamePartTag::AMBIGUOUS,
    NamePartTag::STOP,
];

/// Tags whose parts can receive an `INITIAL` symbol when they
/// consist of a single character.
pub const INITIAL_TAGS: &[NamePartTag] = &[
    NamePartTag::GIVEN,
    NamePartTag::MIDDLE,
    NamePartTag::PATRONYMIC,
    NamePartTag::MATRONYMIC,
];

/// Tags that sit on the given-name side of a name.
pub const GIVEN_NAME_TAGS: &[NamePartTag] = &[
    NamePartTag::GIVEN,
    NamePartTag::MIDDLE,
    NamePartTag::PATRONYMIC,
    NamePartTag::MATRONYMIC,
    NamePartTag::HONORIFIC,
    NamePartTag::STOP,
    NamePartTag::NICK,
];

/// Tags that sit on the family-name side of a name.
pub const FAMILY_NAME_TAGS: &[NamePartTag] = &[
    NamePartTag::PATRONYMIC,
    NamePartTag::MATRONYMIC,
    NamePartTag::FAMILY,
    NamePartTag::SUFFIX,
    NamePartTag::TRIBAL,
    NamePartTag::HONORIFIC,
    NamePartTag::NUM,
    NamePartTag::STOP,
];

/// Canonical display order for name parts by tag.
///
/// Every [`NamePartTag`] variant appears exactly once — consumers can
/// rely on [`NamePartTag::order_index`] never panicking.
pub const NAME_TAGS_ORDER: &[NamePartTag] = &[
    NamePartTag::HONORIFIC,
    NamePartTag::TITLE,
    NamePartTag::GIVEN,
    NamePartTag::MIDDLE,
    NamePartTag::NICK,
    NamePartTag::PATRONYMIC,
    NamePartTag::MATRONYMIC,
    NamePartTag::UNSET,
    NamePartTag::AMBIGUOUS,
    NamePartTag::FAMILY,
    NamePartTag::TRIBAL,
    NamePartTag::NUM,
    NamePartTag::SUFFIX,
    NamePartTag::LEGAL,
    NamePartTag::STOP,
];

impl NamePartTag {
    /// Short stable string key used for downstream serialisation
    /// (logs, index fields). Matches the variant name.
    pub fn value(&self) -> &'static str {
        match self {
            NamePartTag::UNSET => "UNSET",
            NamePartTag::AMBIGUOUS => "AMBIGUOUS",
            NamePartTag::TITLE => "TITLE",
            NamePartTag::GIVEN => "GIVEN",
            NamePartTag::MIDDLE => "MIDDLE",
            NamePartTag::FAMILY => "FAMILY",
            NamePartTag::TRIBAL => "TRIBAL",
            NamePartTag::PATRONYMIC => "PATRONYMIC",
            NamePartTag::MATRONYMIC => "MATRONYMIC",
            NamePartTag::HONORIFIC => "HONORIFIC",
            NamePartTag::SUFFIX => "SUFFIX",
            NamePartTag::NICK => "NICK",
            NamePartTag::STOP => "STOP",
            NamePartTag::NUM => "NUM",
            NamePartTag::LEGAL => "LEGAL",
        }
    }

    /// Position in [`NAME_TAGS_ORDER`] — used as the sort key in
    /// [`crate::names::part::NamePart::tag_sort`]. Infallible; every
    /// variant is in the order array.
    pub fn order_index(&self) -> usize {
        NAME_TAGS_ORDER
            .iter()
            .position(|t| t == self)
            .expect("every NamePartTag variant is in NAME_TAGS_ORDER")
    }

    /// True if this tag is compatible with `other` under the
    /// name-part matching rules:
    ///
    /// * A [wildcard][WILDCARDS] on either side matches anything.
    /// * Equal tags always match.
    /// * Tags restricted to one name-side (given vs. family) only
    ///   match other tags on the same side.
    pub fn can_match(&self, other: NamePartTag) -> bool {
        if WILDCARDS.contains(self) || WILDCARDS.contains(&other) {
            return true;
        }
        if *self == other {
            return true;
        }
        if GIVEN_NAME_TAGS.contains(self) && !GIVEN_NAME_TAGS.contains(&other) {
            return false;
        }
        if FAMILY_NAME_TAGS.contains(self) && !FAMILY_NAME_TAGS.contains(&other) {
            return false;
        }
        true
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl NamePartTag {
    #[getter(value)]
    fn py_value(&self) -> &'static str {
        self.value()
    }

    #[pyo3(name = "can_match")]
    fn py_can_match(&self, other: NamePartTag) -> bool {
        self.can_match(other)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wildcards_match_anything() {
        assert!(NamePartTag::UNSET.can_match(NamePartTag::GIVEN));
        assert!(NamePartTag::GIVEN.can_match(NamePartTag::UNSET));
        assert!(NamePartTag::AMBIGUOUS.can_match(NamePartTag::FAMILY));
        assert!(NamePartTag::STOP.can_match(NamePartTag::NICK));
    }

    #[test]
    fn equal_tags_match() {
        assert!(NamePartTag::GIVEN.can_match(NamePartTag::GIVEN));
        assert!(NamePartTag::FAMILY.can_match(NamePartTag::FAMILY));
    }

    #[test]
    fn given_vs_family_sides_reject() {
        assert!(!NamePartTag::GIVEN.can_match(NamePartTag::FAMILY));
        assert!(!NamePartTag::FAMILY.can_match(NamePartTag::GIVEN));
    }

    #[test]
    fn patronymic_sides() {
        // PATRONYMIC is in both side sets, but the rule rejects a
        // match against any tag that sits in only one side.
        assert!(!NamePartTag::PATRONYMIC.can_match(NamePartTag::GIVEN));
        assert!(!NamePartTag::PATRONYMIC.can_match(NamePartTag::MIDDLE));
        assert!(!NamePartTag::PATRONYMIC.can_match(NamePartTag::FAMILY));
        assert!(NamePartTag::PATRONYMIC.can_match(NamePartTag::MATRONYMIC));
    }

    #[test]
    fn order_covers_every_variant() {
        for t in &[
            NamePartTag::UNSET,
            NamePartTag::AMBIGUOUS,
            NamePartTag::TITLE,
            NamePartTag::GIVEN,
            NamePartTag::MIDDLE,
            NamePartTag::FAMILY,
            NamePartTag::TRIBAL,
            NamePartTag::PATRONYMIC,
            NamePartTag::MATRONYMIC,
            NamePartTag::HONORIFIC,
            NamePartTag::SUFFIX,
            NamePartTag::NICK,
            NamePartTag::STOP,
            NamePartTag::NUM,
            NamePartTag::LEGAL,
        ] {
            let _ = t.order_index();
        }
    }
}
