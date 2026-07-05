---
description: Rework of pair_symbols' covering enumeration — replace the 2^E DFS with conflict-component decomposition, fix output determinism, and catalogue the outstanding pairing-adjacent inconsistencies (input-side span dedup, symbol-id substrate) the rework should account for.
date: 2026-07-05
tags: [rigour, names, pairing, pair-symbols, performance, determinism, rework]
status: drafting
---

# pair_symbols rework

Related plans: `arch-name-pipeline.md` (§ pair_symbols — the output
contract this rework must preserve), `name-matcher-pruning.md` (the
nomenklatura hot loop that makes per-call cost matter).

## Why

`pair_symbols` sits in nomenklatura logic_v2's `match_name_symbolic`
inner loop (`logic_v2/names/match.py:46`), which runs per name-pair
in xref and per query in yente screening — externally supplied
input. The July 2026 audit of `rust/src` found the covering
enumeration is exponential in the number of candidate edges even
when none of them conflict, alongside a handful of smaller
correctness inconsistencies in and around the pairing path. Rather
than patch the DFS in place, rework the enumeration.

## Output contract (must be preserved)

From the current docstrings and NK integration:

- Returns a list of pairings; each pairing is a tuple of
  non-conflicting `Alignment`s (disjoint part coverage per side),
  each with `symbol = Some(_)` and placeholder `score = 1.0`.
- One pairing per `(qmask, rmask, sorted category multiset)`
  equivalence class; distinct category choices on the same parts
  (e.g. a token carrying both `NAME:Qvan` and `SYMBOL:van`)
  surface as separate pairings.
- Every emitted selection is maximal — no un-picked edge is
  compatible with it.
- The empty pairing `[()]` is emitted **only** when there are no
  candidate edges at all (guard trips, no spans, no shared
  symbols). Once any symbol evidence exists we commit to it. This
  is the deliberate "NK-compatible empty-pairing semantics"
  (commit ac23f7d) — callers rely on the list being non-empty.
- Same input → same output, run to run and process to process.
  (Currently violated; see D2.)

## Current pipeline (rust/src/names/pairing.rs)

1. `collect_spans` (:74) — flatten tagger spans to
   `SpanInfo { mask: u64, parts, symbol }`, sorted by `min_idx`.
2. `build_candidate_edges` (:156) — per shared symbol, greedy-bind
   q-spans to r-spans widest-first: `min(N, M)` edges per symbol,
   not N×M. Iterates `q_by_sym: HashMap` (:167) — nondeterministic
   construction order (relevant to D2).
3. `prune_subsumed` (:204) — drop edges strictly dominated (both
   masks strict subsets) within a category.
4. `dedupe_equivalent_edges` (:247) — collapse edges sharing
   `(qmask, rmask, category)`, keep smallest symbol id; re-emits
   via `HashMap::into_values` (:262) — nondeterministic order.
5. `edges.sort_by_cached_key(edge_sort_key)` (:452) — intended to
   restore determinism (but see D2).
6. `enumerate_coverings` / `dfs` (:283-:339) — enumerate maximal
   selections (but see D1).
7. `build_pairing` (:368) — expand masks to `NamePart` refs, reuse
   interned `Py<Symbol>` objects.

## Defects to fix in the rework

### D1 — exponential DFS on non-conflicting edges (issue #223)

`dfs` (:292-:339) unconditionally recurses into the skip-branch
(`dfs(edges, i + 1, …)` at :323) for every edge and rejects
non-maximal selections only at the leaf (:305-:311). With E
pairwise-disjoint edges — the common case — all 2^E subsets are
visited and all but one rejected. Measured (release build): 28-token
person name vs itself → 0.5 s per call; 40 tokens → killed after
2.5 min. The `MAX_PARTS = 64` guard (:36) exists to fit bitmasks in
a `u64`, not to bound enumeration work — it admits inputs needing
~2^40+ leaf visits. The call holds the GIL throughout and never
checks signals, so Python-level timeouts cannot interrupt it.

### D2 — `edge_sort_key` is not a total order → nondeterministic output (unfiled)

`edge_sort_key` (:267-:274) projects masks to
`trailing_zeros()`, collapsing distinct masks that share their
lowest set bit. Edge order entering the sort is nondeterministic
twice over (HashMap iteration in steps 2 and 4 above), and
same-symbol edges with cross-bound masks — e.g. overlapping
same-symbol spans where a `spans_can_pair` rejection forces the
greedy binder into `(q=0b01, r=0b11)` / `(q=0b11, r=0b01)` — survive
both prune (needs strict two-sided domination) and dedupe (masks
differ) yet key identically. Their relative order then varies
run-to-run, changing DFS visit order and hence which selection
first claims its `seen` class (:317) and the output list order.
Fix is free: sort on `(qmask, rmask, category, id)`.

### D3 — input side: `apply_part` dedup starves pairing of spans (unfiled)

`Name.apply_part` → `span_already_applied`
(`rust/src/names/name.rs:229-243`, :460-488) keys its dedup on the
joined span *form* rather than part identity, so the second of two
same-form parts silently gets no span: in `Name("A A Milne")` with
`infer_initials`, only the first "a" carries `INITIAL:a` (verified
live), while `apply_phrase` in the same pipeline covers both
occurrences. Pairing then cannot align the second initial —
coverage loss that looks like a pairing bug but originates upstream.
The dedup exists for repeat tagger runs; it should key on part
hashes (index + form), not the form join.

### D4 — symbol substrate feeding the edges (issues #226, #229)

Not pairing code, but pairing consumes the ids:

- `NUMERIC` symbol ids truncate i64 → u32
  (`rust/src/names/analyze.rs:354`): distinct 10-13-digit registry
  numbers (INN/OGRN) collide into the same symbol → false shared
  edges between unrelated names. Numbers that overflow i64 entirely
  degrade to `comparable = ""` (`rust/src/names/part.rs:41-58`).
- The process-lifetime symbol interner
  (`rust/src/names/symbol.rs:77-106`) grows without bound on those
  data-driven NUMERIC ids via the yente query path.

The rework doesn't have to fix these, but its tests shouldn't bake
in the truncated-id behavior, and a `from_i64`-style constructor
landing for #226 changes `Symbol` equality for numeric edges.

### D5 — guard semantics worth revisiting while in there

- `MAX_PARTS` trips to the empty fallback per *name*; a 65-part
  name silently loses all symbol evidence. Fine as a data-error
  guard, but after D1 the cap exists only for the u64 bitmask —
  decide whether that's still the right representation or whether
  a two-word mask (128 parts) is worth it. (`collect_spans` :91
  already skips indices ≥ 64 from the mask while still counting the
  part — a span whose parts all sit past index 63 would get
  `mask = 0` and pair vacuously; unreachable today only because of
  the entry guard. Keep those two in sync.)
- `spans_can_pair`'s INITIAL single-char rule and NAME/NICK
  cartesian tag check (:121-:140) are matcher policy embedded in
  the binder; unchanged by this rework, but component decomposition
  must apply the same filter before edges enter the graph.

## Rework sketch

Replace `enumerate_coverings` with conflict-component
decomposition:

1. **Conflict graph.** Edges conflict iff `qmask` or `rmask`
   overlap. Build adjacency once — O(E²) mask ANDs, trivial at
   realistic E (post-dedupe E is small; the 28-token repro had 7
   edges after dedupe of 27).
2. **Isolated edges are forced.** Any edge with no conflicts
   belongs to every maximal selection — take it unconditionally.
   This alone makes the common (disjoint) case O(E), restoring
   what the original design promised.
3. **Enumerate within components only.** A maximal global
   selection is the union of one maximal selection per connected
   component (no cross-component conflicts by construction), and
   the global `(qmask, rmask, categories)` dedup key factorizes
   over components. So: enumerate maximal selections per component
   (DFS is fine here — components are where genuine alternatives
   live), dedupe per component, then take the cartesian product
   across components.
4. **Budget the product.** The product can still explode when many
   components each carry alternatives. Cap total emitted pairings
   (proposal: 32) and per-component alternatives (proposal: 8),
   truncating deterministically after sorting alternatives by a
   stable key (e.g. coverage popcount desc, then masks). When a
   single component's own enumeration exceeds an iteration budget,
   degrade to its greedy maximal selection rather than hanging.
   Truncation is a behavior change vs "all equivalence classes" —
   acceptable because downstream scores every pairing and takes a
   max; dropping low-coverage alternatives beyond a bound is
   exactly what a consumer would do anyway. Document the cap in
   the docstring.
5. **Determinism.** Fix `edge_sort_key` to `(qmask, rmask,
   category, id)` (D2); sort component lists and alternatives with
   full-mask keys; no HashMap iteration order may reach the output.
6. **Interruptibility.** With budgets in place the hang class dies;
   optionally also `py.allow_threads` around the pure-Rust
   enumeration (edges are plain data, no Py refs needed until
   `build_pairing`).

Steps 1-3 preserve the output contract exactly (same selections,
same dedup classes); step 4 is the only semantic change and only
under adversarial input.

## Verification

- Existing unit tests in pairing.rs pass unchanged (they cover the
  binder, prune, dedupe, and small DFS cases — none exercise the
  cap).
- New perf test: 40+ disjoint same-category edges complete in
  milliseconds; a component-heavy adversarial case respects the
  pairing cap.
- Determinism test: two runs over names built from shuffled span
  insertion orders produce identical output (catches D2).
- Parity harness: for a corpus of real tagged name pairs (small
  part counts), assert the new enumeration emits the same pairing
  set as the old DFS. Off-corpus, property-check maximality and
  disjointness per emitted pairing.
- D3 fix verified via `analyze_names(PER, ["A A Milne"],
  infer_initials=True)` — both initial parts must carry spans, and
  pairing against "Alan Alexander Milne" must align both.

## Open questions

- Cap values (32 pairings / 8 per component are guesses — check
  the distribution of alternative counts over an xref corpus
  before fixing them).
- On budget overflow: degrade to greedy-per-component (proposed)
  or fall back to `[()]`? Greedy keeps symbol evidence, which
  matches the "commit to evidence" contract better.
- Whether D3 lands inside this rework or as its own change —
  it alters pairing outputs on its own, so sequencing matters for
  the parity harness (fix D3 first, re-baseline, then rework).
