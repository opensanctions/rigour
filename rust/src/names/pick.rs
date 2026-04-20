// Port of `rigour.names.pick.pick_name` and `pick_case`. Hot paths of
// OpenSanctions data export (pick_name runs per entity; pick_case is
// called from `reduce_names` per casefold-group). See
// `plans/rust-pick-name.md` for the design.
//
// ## Division of labour
//
// - `pick_name(names)`: from a bag of multi-script aliases, pick the
//   one most useful to a Latin-literate analyst. Form ranking via
//   weighted Levenshtein centroid (case-insensitive via casefolded
//   forms + ASCII-norm cross-script reinforcement); surface pick
//   within the winning form via the three-level rule
//   `(latin_share DESC, case_error_score ASC, alphabetical ASC)`.
//
// - `pick_case(names)`: from a bag of near-identical names differing
//   only in case, pick the one with the best case quality. Uses the
//   same `case_error_score` as `pick_name`'s surface tiebreak so
//   both paths share a single source of truth.
//
// ## Design notes
//
// An earlier revision of `pick_name` mirrored Python's title-case
// "ballot-box" trick — synthetic `name.title()` variants were pushed
// into the surface bucket to inflate the centroid score of whichever
// surface matched them. That worked on asymmetric inputs but produced
// exact ties on balanced ones (`GAZPROM × N + Gazprom × M`), which
// Python resolved by accidental IEEE-754 rounding order. Replaced
// here with a principled rule: within a winning form, rank candidates
// by latin_share first, then case quality, then alphabetical. All
// three levels are deterministic and reorder-invariant.
//
// A custom `title_case` helper existed to feed the ballot box; it's
// gone. The only remaining caller of casefold here is `casefold` in
// `text::normalize`, which uses ICU4X directly.

use std::collections::{HashMap, HashSet};

use rapidfuzz::distance::levenshtein;

use crate::text::normalize::casefold;
use crate::text::scripts::{codepoint_script, text_scripts};
use crate::text::transliterate::ascii_text;

/// Pick the best display name from a bag of multi-script aliases.
/// Returns `None` iff no usable name survives filtering.
pub fn pick_name(names: &[&str]) -> Option<String> {
    // Sort at intake — determinism across input reorder.
    let mut sorted: Vec<&str> = names.to_vec();
    sorted.sort();

    // Cross-script reinforcement via `ascii_text` is only useful when
    // the input bag spans multiple scripts — it's what lets a Latin
    // "Putin" and a Cyrillic "Путин" vote for the same ASCII form.
    // When every input is in the same script, transliterating each
    // form to ASCII just produces a phantom parallel form table that
    // preserves ranking proportionally and doesn't change any
    // output. Skipping ICU4X entirely in that case is the cheapest
    // way to avoid the 30–50 µs per-non-ASCII-form cost documented in
    // `plans/rust-transliteration.md` under *Downstream-port
    // observations*.
    let mut all_scripts: HashSet<&'static str> = HashSet::new();
    for name in &sorted {
        for script in text_scripts(name) {
            all_scripts.insert(script);
        }
    }
    let cross_script = all_scripts.len() > 1;

    // Per-form weight table, in insertion order.
    let mut weight_keys: Vec<String> = Vec::new();
    let mut weight_idx: HashMap<String, usize> = HashMap::new();
    let mut weights: Vec<f64> = Vec::new();

    // Per-form input-name bucket. Each input name is recorded once
    // per form it contributes to (its direct casefolded form, and
    // optionally its ASCII-norm form if distinct). No synthetic
    // title-cased variants — the final surface pick uses
    // case-quality scoring directly on the real inputs.
    let mut form_candidates: HashMap<String, Vec<String>> = HashMap::new();

    // Track Latin-dominant surfaces for the single-Latin short-circuit.
    let mut latin_names: Vec<String> = Vec::new();

    // Memoise `ascii_text` per form. Cache scope is per-call — inside
    // one `pick_name` the same form appears many times when inputs
    // repeat (OpenSanctions entities typically have 2–20 alias
    // variants with case / script duplicates). The per-thread cache
    // inside `text::ascii_text` handles cross-call repetition.
    let mut norm_cache: HashMap<String, Option<String>> = HashMap::new();

    for name in &sorted {
        // Mirror Python's `name.strip().casefold()`.
        let form = casefold(name.trim());
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
        push_unique(
            form_candidates.entry(form.clone()).or_default(),
            (*name).to_string(),
        );

        if cross_script {
            let norm_entry = norm_cache.entry(form.clone()).or_insert_with(|| {
                let candidate = ascii_text(&form);
                if candidate.chars().count() > 2 {
                    Some(candidate)
                } else {
                    None
                }
            });
            if let Some(norm) = norm_entry.clone() {
                add_weight(
                    &mut weight_keys,
                    &mut weight_idx,
                    &mut weights,
                    &norm,
                    weight,
                );
                // Only push to the norm bucket if it's a *different*
                // key from the direct form — otherwise we'd
                // double-record the same input in the same bucket.
                if norm != form {
                    push_unique(
                        form_candidates.entry(norm).or_default(),
                        (*name).to_string(),
                    );
                }
            }
        }
    }

    if latin_names.len() == 1 {
        return Some(latin_names.into_iter().next().unwrap());
    }

    // Rank forms by weighted Levenshtein centroid.
    let ranked_forms = levenshtein_pick(&weight_keys, &weight_idx, &weights);

    for form in ranked_forms {
        let Some(candidates) = form_candidates.get(&form) else {
            continue;
        };
        if let Some(best) = best_case_candidate(candidates) {
            return Some(best.clone());
        }
    }

    None
}

/// Pick the best case variant from a bag of names expected to be
/// identical apart from case. Port of `rigour.names.pick.pick_case`
/// — returns `None` for empty input (the Python version raises;
/// `Option` is the idiomatic Rust call).
///
/// Score per candidate:
/// - `errors = len`
/// - `+2` for each word-start character that isn't uppercase
/// - `+1` for each mid-word character that is uppercase
///
/// Final score = errors / len. Lower is better. Ties break by length
/// (shorter wins), then by lexicographic order.
pub fn pick_case(names: &[&str]) -> Option<String> {
    match names.len() {
        0 => None,
        1 => Some(names[0].to_string()),
        _ => best_case_string(names).map(str::to_string),
    }
}

/// Deduplicate a name list down to one representative per
/// casefolded form, picking the best case variant in each group.
///
/// Used by zavod's data export pipeline to collapse case-only
/// variants (`"Vladimir Putin"`, `"VLADIMIR PUTIN"`, `"vladimir
/// putin"` → one `"Vladimir Putin"`). Group order follows
/// first-appearance of each casefolded key, so the output is
/// deterministic.
pub fn reduce_names(names: &[&str]) -> Vec<String> {
    if names.len() < 2 {
        return names.iter().map(|s| (*s).to_string()).collect();
    }

    // Preserve first-appearance order via parallel keys + groups
    // vectors keyed through a HashMap index.
    let mut group_idx: HashMap<String, usize> = HashMap::new();
    let mut groups: Vec<Vec<&str>> = Vec::new();
    for name in names {
        let key = casefold(name);
        if let Some(&i) = group_idx.get(&key) {
            groups[i].push(*name);
        } else {
            group_idx.insert(key, groups.len());
            groups.push(vec![*name]);
        }
    }

    let mut out = Vec::with_capacity(groups.len());
    for group in groups {
        // pick_case only returns None on empty input; each group
        // here has ≥1 entry by construction, so the `unwrap_or`
        // branch is unreachable. Kept as a defensive no-op.
        if let Some(picked) = pick_case(&group) {
            out.push(picked);
        } else {
            out.extend(group.iter().map(|s| (*s).to_string()));
        }
    }
    out
}

/// Among `names`, return the one with the best case profile per
/// `case_error_score`. Used by both `pick_case` (full API) and
/// `pick_name` (surface tiebreak within a winning form).
///
/// Ties break by length (shorter wins — biases toward `ß` over
/// `ss`, `Ö` over `Oe`), then by lexicographic order for stability.
fn best_case_string<'a>(names: &'a [&'a str]) -> Option<&'a str> {
    names.iter().copied().min_by(|a, b| {
        let sa = case_error_score(a);
        let sb = case_error_score(b);
        sa.partial_cmp(&sb)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.chars().count().cmp(&b.chars().count()))
            .then_with(|| a.cmp(b))
    })
}

/// Rank `candidates` by the three-level rule and return the top.
/// This is `pick_name`'s surface-within-winning-form selector:
/// prefer Latin readability first, then case quality, then
/// alphabetical stability.
///
/// Unlike `best_case_string`, this accepts cross-script candidates
/// (the winning form may have been populated via both direct
/// casefold and ASCII-norm paths). `latin_share` does the
/// script-preference work before case quality.
fn best_case_candidate(candidates: &[String]) -> Option<&String> {
    candidates.iter().min_by(|a, b| {
        let la = latin_share(a);
        let lb = latin_share(b);
        // Higher latin_share first → reverse compare.
        lb.partial_cmp(&la)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                let sa = case_error_score(a);
                let sb = case_error_score(b);
                sa.partial_cmp(&sb).unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| a.chars().count().cmp(&b.chars().count()))
            .then_with(|| a.cmp(b))
    })
}

/// Per-character case-quality penalty, normalised by length. Lower
/// is better. Direct port of `pick_case`'s inner loop in
/// `rigour/names/pick.py` — length baseline (biases toward
/// shorter), word-start-not-upper adds 2, mid-word-upper adds 1.
/// Non-alphabetic characters reset the word-start flag.
fn case_error_score(s: &str) -> f64 {
    let mut errors: f64 = 0.0;
    let mut total: f64 = 0.0;
    let mut new_word = true;
    for ch in s.chars() {
        total += 1.0;
        // Length-baseline penalty for every char, matching Python.
        errors += 1.0;
        if !ch.is_alphabetic() {
            new_word = true;
            continue;
        }
        if new_word {
            if !ch.is_uppercase() {
                errors += 2.0;
            }
            new_word = false;
            continue;
        }
        if ch.is_uppercase() {
            errors += 1.0;
        }
    }
    if total == 0.0 {
        return 0.0;
    }
    errors / total
}

fn push_unique(bucket: &mut Vec<String>, s: String) {
    if !bucket.iter().any(|existing| existing == &s) {
        bucket.push(s);
    }
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

/// Rank unique entries by weighted Levenshtein centroid. Used only
/// for form ranking; `pick_name`'s surface selection uses
/// `best_case_candidate` instead.
///
/// Duplicates in `entries` aggregate into one bucket per unique
/// string. Deterministic tiebreak: first-appearance order (stable
/// sort on the insertion-ordered key array). We deliberately do
/// NOT reproduce Python's per-position `combinations(entries, 2)`
/// accumulation order — that's a float-rounding accident, not a
/// design choice.
fn levenshtein_pick(
    entries: &[String],
    weight_idx: &HashMap<String, usize>,
    weights: &[f64],
) -> Vec<String> {
    if entries.len() < 2 {
        return entries.to_vec();
    }

    let mut keys: Vec<String> = Vec::new();
    let mut idx: HashMap<String, usize> = HashMap::new();
    let mut counts: Vec<usize> = Vec::new();
    for e in entries {
        if let Some(&i) = idx.get(e) {
            counts[i] += 1;
        } else {
            let i = keys.len();
            idx.insert(e.clone(), i);
            keys.push(e.clone());
            counts.push(1);
        }
    }

    let n_unique = keys.len();
    if n_unique == 1 {
        return keys;
    }

    struct Prepped {
        chars: Vec<char>,
        len: usize,
        weight: f64,
        count: usize,
    }
    let prepped: Vec<Prepped> = keys
        .iter()
        .zip(counts.iter().copied())
        .map(|(s, count)| {
            let chars: Vec<char> = s.chars().collect();
            let len = chars.len();
            let weight = weight_idx
                .get(s)
                .and_then(|&i| weights.get(i).copied())
                .unwrap_or(1.0);
            Prepped {
                chars,
                len,
                weight,
                count,
            }
        })
        .collect();

    // For entry X with count c_X and Y with c_Y, Python's
    // `combinations(entries, 2)` yields C(c_X, 2) self-pairs for X
    // (each contributing 2·w_X since both sides land in edits[X])
    // and c_X·c_Y cross-pairs (X, Y) contributing sim·w_X to X and
    // sim·w_Y to Y. Aggregate directly — O(M²) Levenshtein calls.
    let mut scores: Vec<f64> = vec![0.0; n_unique];
    for i in 0..n_unique {
        let left = &prepped[i];
        let self_pairs = left.count.saturating_sub(1);
        scores[i] += (left.count * self_pairs) as f64 * left.weight;

        let scorer = levenshtein::BatchComparator::new(left.chars.iter().copied());
        for j in (i + 1)..n_unique {
            let right = &prepped[j];
            let distance = scorer.distance(right.chars.iter().copied());
            let base = left.len.max(right.len).max(1);
            let sim = 1.0 - (distance as f64 / base as f64);
            let pair_count = (left.count * right.count) as f64;
            scores[i] += pair_count * sim * left.weight;
            scores[j] += pair_count * sim * right.weight;
        }
    }

    let mut indexed: Vec<(usize, f64)> = (0..n_unique).map(|i| (i, scores[i])).collect();
    indexed.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    indexed.into_iter().map(|(i, _)| keys[i].clone()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---- pick_name ----

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

    #[test]
    fn balanced_case_prefers_title_case() {
        // The case the ballot-box hack used to depend on float luck
        // for. With the case-quality rule, `Gazprom` wins cleanly
        // regardless of input order.
        let a: Vec<&str> = std::iter::repeat_n("GAZPROM", 9)
            .chain(std::iter::repeat_n("Gazprom", 3))
            .collect();
        assert_eq!(pick_name(&a).as_deref(), Some("Gazprom"));

        let b: Vec<&str> = std::iter::repeat_n("Gazprom", 3)
            .chain(std::iter::repeat_n("GAZPROM", 9))
            .collect();
        assert_eq!(pick_name(&b).as_deref(), Some("Gazprom"));
    }

    // ---- pick_case ----

    #[test]
    fn pick_case_empty_and_single() {
        assert_eq!(pick_case(&[]), None);
        assert_eq!(
            pick_case(&["VLADIMIR PUTIN"]).as_deref(),
            Some("VLADIMIR PUTIN")
        );
    }

    #[test]
    fn pick_case_basic_titlecase() {
        let cases = &["Vladimir Putin", "Vladimir PUTIN", "VLADIMIR PUTIN"];
        assert_eq!(pick_case(cases).as_deref(), Some("Vladimir Putin"));
    }

    #[test]
    fn pick_case_weird_mix() {
        let cases = &[
            "Vladimir PuTin",
            "VlaDimir PuTin",
            "Vladimir PUTIN",
            "VLADIMIR PUTIN",
        ];
        assert_eq!(pick_case(cases).as_deref(), Some("Vladimir PuTin"));
    }

    #[test]
    fn pick_case_sharp_s() {
        // Prefers `Stößlein` (shorter, correct case) over the
        // all-caps and SS variants.
        let cases = &[
            "Stefan Stösslein",
            "Stefan Stößlein",
            "Stefan Stößlein",
            "STEFAN STÖSSLEIN",
        ];
        let out = pick_case(cases).unwrap();
        assert!(out.contains("Stößlein"), "got {out:?}");

        let cases = &["Max Strauß", "Max Strauss"];
        let out = pick_case(cases).unwrap();
        assert!(out.contains("Strauß"), "got {out:?}");
    }

    #[test]
    fn pick_case_armenian() {
        let cases = &["Գեւորգ Սամվելի Գորգիսյան", "Գևորգ Սամվելի Գորգիսյան"];
        let out = pick_case(cases).unwrap();
        // Composed form Գևորգ beats decomposed Գեւորգ (both score
        // identically on case-quality, but shorter wins the length
        // tiebreak).
        assert!(out.contains("Գևորգ"), "got {out:?}");
    }

    // ---- reduce_names ----

    #[test]
    fn reduce_names_collapses_case_variants() {
        let names = &[
            "Vladimir Vladimirovich Putin",
            "Vladimir Vladimirovich PUTIN",
            "Vladimir Vladimirovich PUTINY",
            "Vladimir Vladimirovich PUTIN",
        ];
        let reduced = reduce_names(names);
        assert_eq!(reduced.len(), 2);
        assert!(reduced.contains(&"Vladimir Vladimirovich Putin".to_string()));
        assert!(reduced.contains(&"Vladimir Vladimirovich PUTINY".to_string()));
    }

    #[test]
    fn reduce_names_picks_best_case() {
        let names = &["Vladimir Putin", "Vladimir PUTIN", "VLADIMIR PUTIN"];
        assert_eq!(reduce_names(names), vec!["Vladimir Putin".to_string()]);
    }

    #[test]
    fn reduce_names_passthrough_short() {
        assert!(reduce_names(&[]).is_empty());
        assert_eq!(reduce_names(&["."]), vec![".".to_string()]);
        assert_eq!(reduce_names(&["764"]), vec!["764".to_string()]);
    }

    #[test]
    fn reduce_names_greek_case_variants() {
        // `ΚΟΣΜΟΣ`.casefold() yields the non-final sigma, which
        // differs from `Κόσμος`.casefold() by the accent. So these
        // are *two* groups, not one.
        let names = &["Κόσμος", "κόσμος", "κόσμος", "ΚΟΣΜΟΣ"];
        assert_eq!(reduce_names(names).len(), 2);

        // Without the accent, all four collapse to one group.
        let names = &["Κοσμοσ", "κοσμοσ", "κοσμοσ", "ΚΟΣΜΟΣ"];
        assert_eq!(reduce_names(names).len(), 1);
    }

    #[test]
    fn reduce_names_non_name_inputs_passthrough() {
        // Non-alphabetic inputs each form their own group. With
        // `require_names` dropped, nothing filters them out.
        let names = &[".", "6161", " / "];
        assert_eq!(reduce_names(names).len(), 3);
    }

    // ---- case_error_score ----

    #[test]
    fn case_error_orders_variants() {
        // Lower = better. Title Case < ALL-CAPS < all-lower.
        let title = case_error_score("Gazprom");
        let upper = case_error_score("GAZPROM");
        let lower = case_error_score("gazprom");
        assert!(title < upper, "title {title} should be < upper {upper}");
        assert!(title < lower, "title {title} should be < lower {lower}");
    }

    #[test]
    fn case_error_multiword() {
        let good = case_error_score("Robert Smith");
        let shouty = case_error_score("Robert SMITH");
        assert!(good < shouty);
    }
}
