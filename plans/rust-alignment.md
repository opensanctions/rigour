---
description: Port `align_person_name_order` to Rust — the primitive the matcher uses to pair name parts between two presumed-same-person names regardless of presentation order or tokenisation.
date: 2026-04-21
tags: [rigour, rust, names, matching, alignment]
---

# Rust port: `align_person_name_order`

## Why this exists

When the matcher scores two names against each other, it compares
corresponding name parts — "given against given", "family against
family", "middle against middle" — and sums a per-part similarity.
That pairing only makes sense if the parts are in comparable
positions to start with. Real-world names present their parts in
many orders and tokenisations:

* `"John Doe"` vs `"Doe, John"` — order reversed.
* `"Vladimir Vladimirovitch Putin"` vs `"Vladimir Putin"` —
  different part counts; the patronymic is present on one side only.
* `"Ali Al-Sabah"` vs `"Alsabah, Ali"` — same name, different
  tokenisation (hyphenation collapses into one token on one side).
* `"Hans (GIVEN) Friedrich (FAMILY)"` vs `"Hans (FAMILY) Friedrich
  (GIVEN)"` — the same two surface tokens but tagged as swapped
  roles on the two sides.

Naïvely comparing `query.parts[i]` to `result.parts[i]` across these
would report nonsensical distances and tank the match score on pairs
that are obviously the same person. `align_person_name_order`
produces a re-ordering of each side so that `output_left[i]` is the
best match for `output_right[i]`, with extras appended at the end.
Downstream, `nomenklatura/matching/logic_v2/names/match.py:118`
calls it on remaining-parts-after-symbolic-tagging before running
the per-position `weighted_edit_similarity`.

## How the Python impl works today

Location: `rigour/names/alignment.py`.

Greedy best-match loop:

1. Sort each side's unused parts by `len(form)` descending (longest
   first). Biases the search toward distinctive, information-rich
   tokens.
2. Walk the Cartesian product of unused parts, skipping pairs whose
   tags can't match under `NamePartTag.can_match`. Score each pair
   with `dam_levenshtein` over `part.comparable`, normalised by the
   longer string.
3. If one side's token is longer than the other, try to "pack" other
   short parts from the opposite side into the alignment (handles
   the `"Al-Sabah"` vs `"alsabah"` case). `_pack_short_parts` is a
   stable-insertion greedy search: it inserts each tag-compatible
   candidate at the position that maximises the Levenshtein score of
   the packed sequence vs the single long part.
4. Consume the best pair from both `unused` lists, extend the output
   lists, loop. Bail when the best score for this round is `0.0`
   (below a floor defined inside `_name_levenshtein`).
5. Append whatever remained unmatched on each side at the end.

If no match ever fired (best_score stayed 0.0 on the first round),
fall back to `NamePart.tag_sort` on both sides so each side is at
least in a canonical tag order.

## Requirements

### R1. Signature and types

* **R1.1** Takes two lists of `NamePart` (`left`, `right`), returns
  a tuple `(aligned_left, aligned_right)` of the same types.
* **R1.2** Both output lists are permutations (or reindexed copies)
  of the corresponding input lists — no parts created or dropped.
* **R1.3** Works on any `NamePart` regardless of tag; callers pass
  already-tagged parts when they have them and `UNSET` parts when
  they don't.

### R2. Empty and trivial cases

* **R2.1** `align_person_name_order([], [])` → `([], [])`. Tested in
  `test_align_person_special_cases`.
* **R2.2** `align_person_name_order([], right)` → `([],
  NamePart.tag_sort(right))`. Empty-left short-circuit.
* **R2.3** `align_person_name_order(left, [])` — symmetric; current
  code enters the loop but exits immediately (right_unused empty)
  and hits the "no matches found" fall-through, returning
  `(tag_sort(left), tag_sort([]))`. Behaviour to preserve.
* **R2.4** Single-part inputs on both sides of disjoint content
  (`"John"` vs `"Doe"`) return each part unchanged at position 0.
  Tested in `test_align_person_special_cases`.

### R3. Order normalisation for aligned parts

* **R3.1** **Identical content, different order** — `"John Doe"` vs
  `"Doe, John"` → both sides rearranged so each position aligns.
  Test: `test_align_person_name_order` first block.
* **R3.2** **Identical content with tag-swap** —
  `GIVEN"hans" + FAMILY"friedrich"` vs
  `FAMILY"hans" + GIVEN"friedrich"` → outputs re-ordered so the same
  token appears at the same output index on both sides (the tag
  disagreement is surfaced by position, not hidden). Test:
  `test_align_tagged_person_name_parts` final block.
* **R3.3** The concrete output ordering within the aligned prefix is
  **length-descending** on the higher-information side (follows from
  the initial sort). Tests assert specific orderings — the Rust port
  must preserve those exact orderings for matcher parity.

### R4. Asymmetric lengths

* **R4.1** **Query longer** — `"John Richard Smith"` vs
  `"Smith, John"` → `query = [smith, john, richard]`, `result =
  [john, smith]`. The matched prefix aligns; the extra query token
  is appended. Test: third block of `test_align_person_name_order`.
* **R4.2** **Result longer** — `"Vladimir Putin"` vs
  `"Vladimir Vladimirovitch Putin"` → `result` has
  `vladimirovitch` appended at the end. Test: last block of
  `test_align_person_name_order`.
* **R4.3** The extra tokens are appended in the order they appeared
  in the length-descending `unused` list after the matched pairs were
  consumed.

### R5. Fuzzy matching via Damerau-Levenshtein

* **R5.1** Pairs whose `comparable` forms differ by a small edit
  distance should still align — `"John Dow"` vs `"Doe, John"` aligns
  `dow`↔`doe`. Test: second block.
* **R5.2** Similarity threshold is configurable inside the scoring
  helper; today anything scoring below 0.3 is rejected. Preserve
  that floor so alignment doesn't pair genuinely-different parts.
* **R5.3** `part.comparable` is the input to distance — the same
  ASCII-normalised form the matcher uses downstream. Not `form`.

### R6. Part packing for tokenisation differences

* **R6.1** When one side's part is materially longer than the other
  side's candidate, pack tag-compatible short parts from the other
  side into the pairing:
  * `"Ali Al-Sabah"` vs `"Alsabah, Ali"` →
    `query=[ali, al, sabah]`, `result=[ali, alsabah]` — `alsabah`
    pairs against `[al, sabah]` packed together.
  * `"Mohammed Abd Al-Rahman"` vs `"Abdalrahman, Mohammed"` — four
    query parts, two result parts; the `abdalrahman` result token
    absorbs `abd + al + rahman`. Test: first two blocks of
    `test_name_packing`.
* **R6.2** **Non-packable one-token inputs stay unpacked** —
  `"RamiMakhlouf"` (single token) vs `"Maklouf, Ramy"` can't pack in
  either direction and returns one-token-vs-two-token preserved:
  `query=[ramimakhlouf]`, `result=[ramy, maklouf]`. Test: third
  block of `test_name_packing`.
* **R6.3** **Packing respects tags** — `_pack_short_parts` only
  pulls in candidates whose `NamePartTag.can_match` succeeds against
  the anchor part's tag.
* **R6.4** **Packing order is stable-insertion best-score** — each
  candidate is inserted at the position that maximises the
  Levenshtein score of the packed sequence vs the anchor. Preserve
  this to match the Python reference byte-for-byte.
* **R6.5** **Packing stops once the packed length meets or exceeds
  the anchor length** — no over-packing.

### R7. Tag-aware matching

* **R7.1** `NamePartTag.can_match(a, b)` gates every pair under
  consideration — a `GIVEN` part never aligns with a `FAMILY` part
  (except through wildcards). Test:
  `test_align_tagged_person_name_parts` fifth block (`query` with
  mis-tagged parts → output has mismatched forms at same index).
* **R7.2** `UNSET` tags are wildcards and align with any tag on the
  other side. Test: `test_align_tagged_person_name_parts` third
  block — both-UNSET query matches against a GIVEN/FAMILY-tagged
  result.
* **R7.3** Mixed tag sets on one side — e.g. query with a `GIVEN`,
  a `UNSET`, and another `GIVEN` — align each part against the
  best-scoring tag-compatible candidate on the other side. Test:
  fourth block of `test_align_tagged_person_name_parts`.

### R8. Fallback when nothing aligns

* **R8.1** If no pair scored above zero on the first loop iteration,
  return both sides tag-sorted via `NamePart.tag_sort` (default
  canonical ordering). Test: implicit via the test where query and
  result have no character overlap at all ("John" vs "Doe" happens
  to have short scores close to zero; verify which branch is hit).
* **R8.2** The fallback tag-sort respects `NAME_TAGS_ORDER` — the
  same ordering used for display.

### R9. Iteration semantics

* **R9.1** Each part appears in the output exactly once — `unused`
  lists are reduced by removing matched parts before the next
  iteration.
* **R9.2** Length of each output list equals the length of its
  input list. Tested explicitly in every block of every test via
  `len(query_sorted)` / `len(result_sorted)` assertions.
* **R9.3** Iteration is deterministic given the same inputs — the
  sort + product order is stable.

### R10. Performance

* **R10.1** Worst-case `O(n × m × max(n,m))` where `n`/`m` are the
  part counts on each side — Cartesian product per iteration.
* **R10.2** Typical inputs are small (2–5 parts per side), so the
  absolute cost is dominated by per-pair `dam_levenshtein`. The
  Rust port should use the crate-internal `rapidfuzz` Levenshtein
  already wired up for `pick_name`, not call back into Python.
* **R10.3** No FFI crossing during the loop. The function takes a
  list of Rust `NamePart` objects and returns the same.

## What to rename / drop on the port

* Keep the function name `align_person_name_order` — nomenklatura
  imports it by that exact name.
* `_name_levenshtein` and `_pack_short_parts` are private helpers
  and can be inlined or rewired freely.
* The `_name_levenshtein` score-floor of `0.3` is a magic number in
  the Python code — port as a named `const` with a comment on what
  it was tuned against.

## Non-goals

* Not porting the matching / scoring pipeline that consumes the
  aligned output — this is a layout primitive only.
* Not changing the set of side effects / semantics — the Rust port
  should produce byte-identical output for every existing Python
  test case. Any divergence is a regression.
* Not adding new kwargs. If the matcher wants a different scoring
  floor later, that's a separate change.
* Not handling non-person names. The function is intentionally
  person-specific; nomenklatura's matcher switches to
  `NamePart.tag_sort` for ORG/ENT/OBJ names
  (`match.py:119-121`).

## Open questions

1. **Determinism vs score-threshold edge cases** — `_name_levenshtein`
   returns `1.0` when `query_str == result_str` OR when `max_len ==
   0`. The latter case (two empty-comparable parts) returns 1.0 and
   would short-circuit the best-score search. Is that desirable?
   The Python code has shipped this way; likely intentional. Port
   verbatim, document.
2. **Does `NamePart.tag_sort` on the fallback branch need to be
   stable across ties?** Yes — `NAME_TAGS_ORDER` gives a total
   ordering, so as long as the sort within a tag is stable, output
   is deterministic.
3. **R8.1 behaviour audit** — the Python code reaches the
   `if not len(left_sorted)` branch after the loop. Need to verify
   under what inputs this branch actually fires vs R4's
   "some matches but not all" path.
