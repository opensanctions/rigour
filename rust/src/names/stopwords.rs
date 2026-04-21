// Rust-side ownership of `resources/names/stopwords.yml` → exposes
// five flat wordlists to Python. The YAML file's name is misleading
// (contents are prefixes + split phrases + generic full names, not
// stopwords); kept for now to minimise diff.
//
// Python consumers:
//   - `rigour.names.prefix` — reads `person_name_prefixes_list`,
//     `org_name_prefixes_list`, `obj_name_prefixes_list`.
//   - `rigour.names.split_phrases` — reads `name_split_phrases_list`.
//   - `rigour.names.check` — reads `generic_person_names_list`.

use serde::Deserialize;
use std::sync::LazyLock;

#[derive(Debug, Deserialize)]
struct NameStopwords {
    person_name_prefixes: Vec<String>,
    org_name_prefixes: Vec<String>,
    obj_name_prefixes: Vec<String>,
    name_split_phrases: Vec<String>,
    generic_person_names: Vec<String>,
}

const JSON: &str = include_str!("../../data/names/stopwords.json");

static DATA: LazyLock<NameStopwords> =
    LazyLock::new(|| serde_json::from_str(JSON).expect("rust/data/names/stopwords.json parses"));

pub fn person_name_prefixes_list() -> Vec<String> {
    DATA.person_name_prefixes.clone()
}

pub fn org_name_prefixes_list() -> Vec<String> {
    DATA.org_name_prefixes.clone()
}

pub fn obj_name_prefixes_list() -> Vec<String> {
    DATA.obj_name_prefixes.clone()
}

pub fn name_split_phrases_list() -> Vec<String> {
    DATA.name_split_phrases.clone()
}

pub fn generic_person_names_list() -> Vec<String> {
    DATA.generic_person_names.clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn data_loads_and_all_lists_nonempty() {
        assert!(!person_name_prefixes_list().is_empty());
        assert!(!org_name_prefixes_list().is_empty());
        assert!(!obj_name_prefixes_list().is_empty());
        assert!(!name_split_phrases_list().is_empty());
        assert!(!generic_person_names_list().is_empty());
    }
}
