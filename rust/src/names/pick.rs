// Port of `rigour.names.pick.pick_name`. Hot path of OpenSanctions
// data export — runs per entity to choose the display name from a bag
// of multi-script aliases. See `plans/rust-pick-name.md` for the
// port plan and `tests/names/test_pick.py` for the behavioural
// contract.
//
// ## Design
//
// The function bundles three scoring ideas:
//
//   1. **Latin-readability bias.** Each name gets a weight `1 +
//      latin_share`, where Cyrillic/Greek chars count as 0.3 Latin
//      (close enough for an analyst to muddle through) and other
//      scripts count as 0.
//   2. **Cross-script reinforcement.** Each name's casefolded form
//      plus its `ascii_text` transliteration are both indexed as
//      forms with the same weight — so Latin "Putin", Cyrillic
//      "Путин", Ukrainian "Путін" all vote for the ASCII "putin"
//      cluster in addition to their own script cluster.
//   3. **Levenshtein centroid.** Within the form table and within a
//      winning form's surfaces, similarity-weighted voting picks the
//      one most alike to the others.
//
// ## Parity requirements
//
// - Input is sorted first (determinism; matches Python `sorted(names)`).
// - Insertion order of forms into the weight table matters for
//   tiebreaks. We preserve it via a `Vec<(String, f64)>` paired with a
//   `HashMap<String, usize>` index — cheaper than pulling in an
//   `IndexMap` dep.
// - `.title()` variants of each surface are added to the form's
//   surface bucket so Title Case wins tiebreaks against ALL-CAPS /
//   all-lower when a Title Case variant is in the input.
// - Return value must be a literal element of the input list.
//
// See the Python source (`rigour/names/pick.py`) for the exact
// per-step semantics we mirror.

use std::collections::{HashMap, HashSet};

use rapidfuzz::distance::levenshtein;

use crate::text::scripts::codepoint_script;
use crate::text::transliterate::ascii_text;

/// Pick the best display name from a bag of multi-script aliases.
/// Returns `None` iff no usable name survives filtering.
pub fn pick_name(names: &[&str]) -> Option<String> {
    // Sort at intake — determinism across input reorder.
    let mut sorted: Vec<&str> = names.to_vec();
    sorted.sort();

    // Per-form weight table, in insertion order.
    let mut weight_keys: Vec<String> = Vec::new();
    let mut weight_idx: HashMap<String, usize> = HashMap::new();
    let mut weights: Vec<f64> = Vec::new();

    // Per-form surface bucket, in insertion order.
    let mut form_surfaces: HashMap<String, Vec<String>> = HashMap::new();

    // Track the set of Latin-dominant surfaces for the single-Latin
    // short-circuit.
    let mut latin_names: Vec<String> = Vec::new();

    // Memoise `ascii_text` per form. Python's `rigour.text.ascii_text`
    // carries an `MEMO_LARGE` LRU so recomputing on repeat forms is
    // cheap; our Rust `text::ascii_text` has no process-level cache,
    // only a thread-local transliterator pool. In this function the
    // same form appears many times when inputs repeat (a typical
    // OpenSanctions entity has 2–20 alias variants, many case or
    // script duplicates), so memoise here — saves an ICU4X roundtrip
    // per repeat.
    //
    // `Option<String>`: `None` marks "already computed, not useful"
    // (length ≤ 2) so we skip the form-add path on every repeat.
    let mut norm_cache: HashMap<String, Option<String>> = HashMap::new();

    for name in &sorted {
        let form = casefold_strip(name);
        if form.is_empty() {
            continue;
        }

        let latin_shr = latin_share(name);
        if latin_shr > 0.85 {
            latin_names.push((*name).to_string());
        }
        let weight = 1.0 + latin_shr;

        add_weight(
            &mut weight_keys,
            &mut weight_idx,
            &mut weights,
            &form,
            weight,
        );
        let bucket = form_surfaces.entry(form.clone()).or_default();
        bucket.push((*name).to_string());
        bucket.push(title_case(name));

        let norm = norm_cache.entry(form.clone()).or_insert_with(|| {
            let candidate = ascii_text(&form);
            if candidate.chars().count() > 2 {
                Some(candidate)
            } else {
                None
            }
        });
        if let Some(norm) = norm.clone() {
            add_weight(
                &mut weight_keys,
                &mut weight_idx,
                &mut weights,
                &norm,
                weight,
            );
            form_surfaces
                .entry(norm)
                .or_default()
                .push((*name).to_string());
        }
    }

    if latin_names.len() == 1 {
        return Some(latin_names.into_iter().next().unwrap());
    }

    // Rank forms by weighted Levenshtein centroid.
    let ranked_forms = levenshtein_pick(&weight_keys, &weight_idx, &weights);

    // Input-membership set for the "must be in names" final check.
    let input_set: HashSet<&str> = names.iter().copied().collect();

    for form in ranked_forms {
        let Some(surfaces) = form_surfaces.get(&form) else {
            continue;
        };
        // Inner pick: unweighted centroid across the surface bucket.
        // Empty weight map → every surface gets implicit weight 1.0.
        let inner_idx: HashMap<String, usize> = HashMap::new();
        let inner_weights: Vec<f64> = Vec::new();
        let ranked_surfaces = levenshtein_pick(surfaces, &inner_idx, &inner_weights);
        for surface in ranked_surfaces {
            if input_set.contains(surface.as_str()) {
                return Some(surface);
            }
        }
    }

    None
}

fn casefold_strip(s: &str) -> String {
    // Mirror Python's `s.strip().casefold()`. Stripping uses Python's
    // "whitespace" definition (Unicode White_Space); Rust `str::trim`
    // uses `char::is_whitespace` which is the same property. Casefold
    // uses ICU full casefold, already Rust-backed via the normalize
    // module — but we import it lazily to avoid churn.
    use crate::text::normalize::{Cleanup, Normalize, normalize};
    normalize(s, Normalize::STRIP | Normalize::CASEFOLD, Cleanup::Noop).unwrap_or_default()
}

fn title_case(s: &str) -> String {
    // Python's `str.title()` uppercases the first letter of each "word"
    // (sequence following a non-alphabetic character) and lowercases
    // the rest. Mirror its behaviour — this is surface-bias scaffolding,
    // not a user-facing primitive, so exact parity matters only for
    // what the levenshtein picker sees.
    let mut out = String::with_capacity(s.len());
    let mut prev_alpha = false;
    for c in s.chars() {
        if c.is_alphabetic() {
            if prev_alpha {
                out.extend(c.to_lowercase());
            } else {
                out.extend(c.to_uppercase());
            }
            prev_alpha = true;
        } else {
            out.push(c);
            prev_alpha = false;
        }
    }
    out
}

// Unicode scripts where chars count as 0.3 Latin (close enough for an
// analyst accustomed to the Latin alphabet). Mirrors
// `_LATIN_SHARE_PARTIAL` in the Python source.
fn partial_latin_score(script: &str) -> f64 {
    match script {
        "Latin" => 1.0,
        "Cyrillic" | "Greek" => 0.3,
        _ => 0.0,
    }
}

fn latin_share(text: &str) -> f64 {
    let mut latin = 0.0f64;
    let mut alpha = 0usize;
    for c in text.chars() {
        if !c.is_alphabetic() {
            continue;
        }
        alpha += 1;
        if let Some(script) = codepoint_script(c as u32) {
            latin += partial_latin_score(script);
        }
    }
    if alpha == 0 {
        0.0
    } else {
        latin / alpha as f64
    }
}

fn add_weight(
    keys: &mut Vec<String>,
    idx: &mut HashMap<String, usize>,
    weights: &mut Vec<f64>,
    key: &str,
    weight: f64,
) {
    if let Some(&i) = idx.get(key) {
        weights[i] += weight;
    } else {
        let i = keys.len();
        keys.push(key.to_string());
        weights.push(weight);
        idx.insert(key.to_string(), i);
    }
}

/// Rank entries by weighted Levenshtein centroid. Each pair `(left,
/// right)` contributes `sim × weight[left]` to `left`'s score and
/// `sim × weight[right]` to `right`'s score, where
/// `sim = 1 - distance / max(len_left, len_right, 1)`. Entries absent
/// from the weight map get weight `1.0`. Mirrors `_levenshtein_pick`
/// in the Python source.
///
/// Duplicates in `entries` aggregate into one bucket per unique
/// string — the Python implementation keys scores by string via a
/// `defaultdict(float)`. Per-string aggregation also avoids
/// float-accumulation order drift that made per-position tied scores
/// break ties inconsistently.
///
/// Returns **unique** entry strings sorted by score descending. Ties
/// preserve insertion order (first pair where a string appears as
/// either side).
fn levenshtein_pick(
    entries: &[String],
    weight_idx: &HashMap<String, usize>,
    weights: &[f64],
) -> Vec<String> {
    if entries.len() < 2 {
        return entries.to_vec();
    }

    // Dedupe with first-appearance order; keep a position → unique-
    // index map so the scoring loop can iterate pairs in Python's
    // `combinations(entries, 2)` order without repeatedly hashing
    // strings.
    let mut keys: Vec<String> = Vec::new();
    let mut key_of_entry: HashMap<String, usize> = HashMap::new();
    let mut position_key: Vec<usize> = Vec::with_capacity(entries.len());
    for e in entries {
        let i = match key_of_entry.get(e) {
            Some(&i) => i,
            None => {
                let i = keys.len();
                keys.push(e.clone());
                key_of_entry.insert(e.clone(), i);
                i
            }
        };
        position_key.push(i);
    }

    let n_unique = keys.len();
    if n_unique == 1 {
        return keys;
    }

    // Per-unique precompute: char Vec + length + weight.
    struct Prepped {
        chars: Vec<char>,
        len: usize,
        weight: f64,
    }
    let prepped: Vec<Prepped> = keys
        .iter()
        .map(|s| {
            let chars: Vec<char> = s.chars().collect();
            let len = chars.len();
            let weight = weight_idx
                .get(s)
                .and_then(|&i| weights.get(i).copied())
                .unwrap_or(1.0);
            Prepped { chars, len, weight }
        })
        .collect();

    // O(M²) similarity matrix over unique strings. With N entries
    // containing many duplicates this avoids the O(N²) Levenshtein
    // call count Python has to pay. Each `BatchComparator` is a
    // single allocation reused against every right below it.
    //
    // Stored as a flat Vec indexed `row * n + col`. Self-sim is 1.0
    // (diagonal), matrix is symmetric.
    let mut sim_matrix: Vec<f64> = vec![0.0; n_unique * n_unique];
    for i in 0..n_unique {
        sim_matrix[i * n_unique + i] = 1.0;
        let scorer = levenshtein::BatchComparator::new(prepped[i].chars.iter().copied());
        for j in (i + 1)..n_unique {
            let distance = scorer.distance(prepped[j].chars.iter().copied());
            let base = prepped[i].len.max(prepped[j].len).max(1);
            let sim = 1.0 - (distance as f64 / base as f64);
            sim_matrix[i * n_unique + j] = sim;
            sim_matrix[j * n_unique + i] = sim;
        }
    }

    // Score accumulation matching Python's pair-by-pair order so
    // float-rounding ties break identically. Scores are keyed by
    // unique-string index, but we iterate all (i, j) position pairs
    // in `entries` to reproduce the exact add sequence that Python's
    // `combinations(entries, 2)` produces.
    let mut scores: Vec<f64> = vec![0.0; n_unique];
    for (i, &ki) in position_key.iter().enumerate() {
        for &kj in &position_key[i + 1..] {
            let sim = sim_matrix[ki * n_unique + kj];
            scores[ki] += sim * prepped[ki].weight;
            scores[kj] += sim * prepped[kj].weight;
        }
    }

    let mut indexed: Vec<(usize, f64)> = (0..n_unique).map(|i| (i, scores[i])).collect();
    // Stable sort by score descending — ties keep insertion order.
    indexed.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    indexed.into_iter().map(|(i, _)| keys[i].clone()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_inputs() {
        assert_eq!(pick_name(&[]), None);
        assert_eq!(pick_name(&[""]), None);
        assert_eq!(pick_name(&["", "   ", ""]), None);
    }

    #[test]
    fn single_input() {
        assert_eq!(pick_name(&["Putin"]).as_deref(), Some("Putin"));
    }

    #[test]
    fn single_latin_short_circuits() {
        let names = &["Vladimir Putin", "Владимир Путин", "Владимир Путин"];
        assert_eq!(pick_name(names).as_deref(), Some("Vladimir Putin"));
    }

    #[test]
    fn titlecase_bias() {
        let names = &[
            "Vladimir Vladimirovich Putin",
            "Vladimir Vladimirovich PUTIN",
            "Vladimir Vladimirovich PUTIN",
        ];
        let got = pick_name(names).unwrap();
        assert!(got.contains("Putin"), "got {got:?}");
    }

    #[test]
    fn cross_script_centroid() {
        let names = &[
            "Mitch McConnell",
            "Mičs Makonels",
            "Митч Макконнелл",
            "ميتش ماكونيل",
            "ミッチ・マコーネル",
            "미치 매코널",
        ];
        assert_eq!(pick_name(names).as_deref(), Some("Mitch McConnell"));
    }

    #[test]
    fn deterministic_across_reorder() {
        let a = &[
            "OCEAN SHIP MANAGEMENT AND OPERATION LLC",
            "OCEAN SHIP MANAGEMENT and OPERATION LLC",
        ];
        let b = &[
            "OCEAN SHIP MANAGEMENT and OPERATION LLC",
            "OCEAN SHIP MANAGEMENT AND OPERATION LLC",
        ];
        assert_eq!(pick_name(a), pick_name(b));
    }

    #[test]
    fn dirty_inputs() {
        let names = &["", "PETER", "Peter"];
        assert_eq!(pick_name(names).as_deref(), Some("Peter"));
    }
}
