// Prefix removers for person / org / object names. Port of
// `rigour.names.prefix` — each function strips a leading run of
// honorific / article prefixes from the input.
//
// The Python impl compiles a regex of the shape
//   ^\W*((alt1|alt2|...)\.?\s+)*
// with case-insensitive + Unicode flags, and calls `.sub("", name)`.
// We mirror that precisely here using the `regex` crate. No
// lookarounds, so `regex` is a fit (unlike the org-types pipeline
// which needs Python-style `(?<!\w)X(?!\w)` boundaries and goes
// through `Needles` instead).

use std::sync::LazyLock;

use regex::Regex;

use crate::names::stopwords::{
    obj_name_prefixes_list, org_name_prefixes_list, person_name_prefixes_list,
};

fn build_prefix_regex(prefixes: &[String]) -> Regex {
    let escaped: Vec<String> = prefixes.iter().map(|p| regex::escape(p)).collect();
    let joined = escaped.join("|");
    // (?i) = case-insensitive. `\W` in `regex` with Unicode enabled
    // already matches non-word Unicode chars, same as Python's
    // `re.I | re.U`. `\W*` at the front eats a leading run of
    // punctuation / whitespace, then `((alt|alt|...)\.?\s+)*`
    // consumes one-or-more prefix tokens each followed by optional
    // `.` and required whitespace.
    let pattern = format!(r"(?i)^\W*(({})\.?\s+)*", joined);
    Regex::new(&pattern).expect("prefix regex compiles")
}

static PERSON_PREFIX_RE: LazyLock<Regex> =
    LazyLock::new(|| build_prefix_regex(&person_name_prefixes_list()));

static ORG_PREFIX_RE: LazyLock<Regex> =
    LazyLock::new(|| build_prefix_regex(&org_name_prefixes_list()));

static OBJ_PREFIX_RE: LazyLock<Regex> =
    LazyLock::new(|| build_prefix_regex(&obj_name_prefixes_list()));

/// Remove honorific prefixes like "Mr.", "Mrs.", "Dr." from the head
/// of a person name.
pub fn remove_person_prefixes(name: &str) -> String {
    PERSON_PREFIX_RE.replace(name, "").into_owned()
}

/// Remove article-like prefixes like "The" from the head of an
/// organisation name.
pub fn remove_org_prefixes(name: &str) -> String {
    ORG_PREFIX_RE.replace(name, "").into_owned()
}

/// Remove object-name prefixes like "MV", "The" from the head of an
/// object name (vessel, security, etc).
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
}
