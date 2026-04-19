// Territory records loader.
//
// `rust/data/territories/data.jsonl` is the full territory database:
// one JSON record per line, fields `{code, name, full_name, alpha3,
// qid, parent, is_country, is_jurisdiction, is_historical, langs,
// names_strong, names_weak, ...}`. Authoritative emission is
// `genscripts/generate_territories.py::update_data`. This module
// exposes the raw JSONL text so Python (`rigour.territories.*`) and
// the future Rust tagger consume it without needing filesystem
// access at runtime.

const JSONL: &str = include_str!("../data/territories/data.jsonl");

/// Return the full territories JSONL as `&'static str`. Python-side
/// consumers parse line-by-line with orjson; the Rust tagger reads
/// through serde into typed structs when step 8 lands.
pub fn raw() -> &'static str {
    JSONL
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_and_has_records() {
        let text = raw();
        assert!(!text.is_empty());
        let lines: Vec<&str> = text.lines().filter(|l| !l.is_empty()).collect();
        assert!(
            lines.len() > 100,
            "expected >100 territory records, got {}",
            lines.len()
        );
        // Every line should be a JSON object starting with `{`.
        for line in &lines {
            assert!(
                line.starts_with('{'),
                "expected JSON object per line, got: {}",
                &line[..line.len().min(40)]
            );
        }
    }
}
