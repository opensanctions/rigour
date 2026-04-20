// Rust-native versions of `NameTypeTag` and `NamePartTag`, ported
// from `rigour/names/tag.py`. Mirrors the `SymbolCategory` pattern:
// sealed enums exposed to Python as `#[pyclass]` types, variant
// names match the Python attribute set exactly (SCREAMING_SNAKE_CASE
// so no `#[pyo3(name = ...)]` renames are needed).
//
// The auxiliary Python constants (`WILDCARDS`, `INITIAL_TAGS`,
// `GIVEN_NAME_TAGS`, `FAMILY_NAME_TAGS`, `NAME_TAGS_ORDER`) stay on
// the Python side — `rigour/names/tag.py` rebuilds them from the
// Rust-exposed variants so downstream `part.tag in INITIAL_TAGS`
// membership checks keep working unchanged.

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// What kind of thing a name describes. Mirrors the pre-port
/// `rigour.names.tag.NameTypeTag` string-valued enum.
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
    /// Pre-port Python `.value` string — downstream uses this as a
    /// stable serialisation key.
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

/// Within a name, identify name-part types. Mirrors the pre-port
/// `rigour.names.tag.NamePartTag`.
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

/// Tags whose semantics mean "match anything" during part-tagging.
/// Mirrors `rigour.names.tag.WILDCARDS`.
pub const WILDCARDS: &[NamePartTag] = &[
    NamePartTag::UNSET,
    NamePartTag::AMBIGUOUS,
    NamePartTag::STOP,
];

/// Tags eligible for INITIAL-symbol promotion on single-char parts.
/// Mirrors `rigour.names.tag.INITIAL_TAGS`.
pub const INITIAL_TAGS: &[NamePartTag] = &[
    NamePartTag::GIVEN,
    NamePartTag::MIDDLE,
    NamePartTag::PATRONYMIC,
    NamePartTag::MATRONYMIC,
];

/// Tags that sit on the given-name side of a name. Mirrors
/// `rigour.names.tag.GIVEN_NAME_TAGS`.
pub const GIVEN_NAME_TAGS: &[NamePartTag] = &[
    NamePartTag::GIVEN,
    NamePartTag::MIDDLE,
    NamePartTag::PATRONYMIC,
    NamePartTag::MATRONYMIC,
    NamePartTag::HONORIFIC,
    NamePartTag::STOP,
    NamePartTag::NICK,
];

/// Tags that sit on the family-name side of a name. Mirrors
/// `rigour.names.tag.FAMILY_NAME_TAGS`.
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

/// Canonical sort order for display — used by `NamePart.tag_sort`.
/// Mirrors `rigour.names.tag.NAME_TAGS_ORDER`.
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

    /// Position in `NAME_TAGS_ORDER` — used for sorting. Since
    /// every variant appears in that array the lookup is infallible.
    pub fn order_index(&self) -> usize {
        NAME_TAGS_ORDER
            .iter()
            .position(|t| t == self)
            .expect("every NamePartTag variant is in NAME_TAGS_ORDER")
    }

    /// Mirrors the Python `NamePartTag.can_match`:
    ///   * wildcards on either side → True
    ///   * equal tags → True
    ///   * otherwise, tags on opposite name-sides → False
    ///   * default → True
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
    fn given_vs_family_sides_cannot_match() {
        // GIVEN is on the given side; FAMILY is on the family side.
        // Neither is a wildcard. Both sides reject.
        assert!(!NamePartTag::GIVEN.can_match(NamePartTag::FAMILY));
        assert!(!NamePartTag::FAMILY.can_match(NamePartTag::GIVEN));
    }

    #[test]
    fn patronymic_pickings() {
        // PATRONYMIC is in both side sets but the asymmetric gates
        // reject matches against tags that sit in only one side.
        // GIVEN is GIVEN-side only — reject.
        assert!(!NamePartTag::PATRONYMIC.can_match(NamePartTag::GIVEN));
        // MIDDLE is GIVEN-side only (not in FAMILY_NAME_TAGS) — reject.
        assert!(!NamePartTag::PATRONYMIC.can_match(NamePartTag::MIDDLE));
        // MATRONYMIC is in both side sets — accept.
        assert!(NamePartTag::PATRONYMIC.can_match(NamePartTag::MATRONYMIC));
        // FAMILY is FAMILY-side only; PATRONYMIC also in FAMILY side
        // — the "self in GIVEN, other not in GIVEN" gate fires:
        // FAMILY is not in GIVEN_NAME_TAGS → reject.
        assert!(!NamePartTag::PATRONYMIC.can_match(NamePartTag::FAMILY));
    }

    #[test]
    fn order_covers_every_variant() {
        // Every declared NamePartTag must have an order position,
        // or NamePart.tag_sort would panic on unordered tags.
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
