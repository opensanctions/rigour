//! Leading-prefix removers for person, organisation, and object
//! names — strip honorifics, articles, and vessel-class markers from
//! the head of a name before matching or indexing.

use std::sync::LazyLock;

use regex::Regex;

use crate::names::stopwords::{
    obj_name_prefixes_list, org_name_prefixes_list, person_name_prefixes_list,
};

fn build_prefix_regex(prefixes: &[String]) -> Regex {
    // Escape alternatives, join with `|`, wrap in the Python-compatible
    // anchored shape: `^\W*((alt|alt|...)\.?\s+)*`. Matches an optional
    // leading punctuation run, then zero-or-more prefix tokens each
    // followed by an optional `.` and required whitespace.
    let joined = prefixes
        .iter()
        .map(|p| regex::escape(p))
        .collect::<Vec<_>>()
        .join("|");
    let pattern = format!(r"(?i)^\W*(({})\.?\s+)*", joined);
    Regex::new(&pattern).expect("prefix regex compiles")
}

static PERSON_PREFIX_RE: LazyLock<Regex> =
    LazyLock::new(|| build_prefix_regex(&person_name_prefixes_list()));

static ORG_PREFIX_RE: LazyLock<Regex> =
    LazyLock::new(|| build_prefix_regex(&org_name_prefixes_list()));

static OBJ_PREFIX_RE: LazyLock<Regex> =
    LazyLock::new(|| build_prefix_regex(&obj_name_prefixes_list()));

/// Strip honorific prefixes ("Mr.", "Mrs.", "Dr.", "Lady", …) from
/// the head of a person name. Called before analysing or matching to
/// stop honorifics from contaminating part alignment.
pub fn remove_person_prefixes(name: &str) -> String {
    PERSON_PREFIX_RE.replace(name, "").into_owned()
}

/// Strip article-like prefixes ("The", …) from the head of an
/// organisation name. Drops "The Charitable Trust" → "Charitable
/// Trust" so matching doesn't penalise the shorter variant.
pub fn remove_org_prefixes(name: &str) -> String {
    ORG_PREFIX_RE.replace(name, "").into_owned()
}

/// Strip vessel-class markers ("M/V", "SS", …) and generic articles
/// from the head of an object name. `"M/V Oceanic"` → `"Oceanic"`.
pub fn remove_obj_prefixes(name: &str) -> String {
    OBJ_PREFIX_RE.replace(name, "").into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn person_prefix_dropped() {
        assert_eq!(remove_person_prefixes("Mr. John Smith"), "John Smith");
        assert_eq!(remove_person_prefixes("Mrs Mary Doe"), "Mary Doe");
    }

    #[test]
    fn person_prefix_case_insensitive() {
        assert_eq!(remove_person_prefixes("MR. John Smith"), "John Smith");
        assert_eq!(remove_person_prefixes("dr John Smith"), "John Smith");
    }

    #[test]
    fn person_prefix_no_match_is_identity() {
        assert_eq!(remove_person_prefixes("John Smith"), "John Smith");
    }

    #[test]
    fn org_prefix_dropped() {
        assert_eq!(remove_org_prefixes("The Acme Corp"), "Acme Corp");
    }

    #[test]
    fn org_prefix_no_match_is_identity() {
        assert_eq!(remove_org_prefixes("Acme Corp"), "Acme Corp");
    }

    #[test]
    fn obj_prefix_dropped() {
        assert_eq!(remove_obj_prefixes("M/V Oceanic"), "Oceanic");
    }
}
