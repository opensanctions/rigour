---
description: First-principles rework of pair_symbols — requirements derived from the nomenklatura consumer, formal framing (maximal-independent-set enumeration), comparison of candidate approaches, and the chosen conflict-component decomposition; plus the catalogue of pairing-adjacent defects (exponential DFS, nondeterministic ordering, input-side span dedup, symbol-id substrate).
date: 2026-07-05
tags: [rigour, names, pairing, pair-symbols, performance, determinism, rework]
status: drafting
---

# pair_symbols rework

Related plans: `arch-name-pipeline.md` (§ pair_symbols, § Alignment —
the object model this rework operates on), `name-matcher-pruning.md`
(the nomenklatura hot loop that makes per-call cost matter).

## Why

`pair_symbols` sits in nomenklatura logic_v2's `match_name_symbolic`
inner loop (`logic_v2/names/match.py:46`), which runs per name-pair
in xref and per query in yente screening — externally supplied
input. The July 2026 audit of `rust/src` found the covering
enumeration is exponential in the number of candidate edges even
when none of them conflict, alongside a handful of smaller
correctness inconsistencies in and around the pairing path. Rather
than patch the DFS in place, re-derive what the function must do
from its consumer and pick the implementation that fits.

## What pair_symbols is actually for

Reading `match_name_symbolic` end to end, the function's real job
is narrower than "enumerate all coverings":

**It produces the candidate set for a downstream argmax whose
objective function rigour does not know.** For each pairing, NK:

1. prices each symbol edge by category (`SYM_SCORES` /
   `SYM_WEIGHTS` in `magic.py` — e.g. NAME → score 0.9 / weight
   1.0, NICK → 0.6 / 0.8, SYMBOL → 0.9 / 0.3);
2. runs `compare_parts` (a Levenshtein DP) over the *uncovered*
   parts of both sides — the residue;
3. applies policy passes (extras weights, stopword multiplier,
   literal-equality rescue, family-name boost);
4. computes `score = Σ(sᵢ·wᵢ) / Σ(wᵢ)` and keeps the maximum
   over pairings, early-exiting at 1.0.

Two structural facts follow:

- **The objective is not additive.** It's a ratio (weighted mean),
  and the residue term couples all uncovered parts through one
  global DP. So the best choice inside one ambiguous region of the
  name depends on everything else in both names. rigour cannot
  resolve ambiguity locally without the score tables *and* the
  residue distance — which is why enumeration of scoring-distinct
  alternatives is a genuine requirement, not over-engineering.
- **Every emitted pairing costs the consumer a `compare_parts` DP
  plus a policy pass.** Output cardinality is therefore part of the
  performance budget, same as enumeration cost inside rigour.
  A "correct" enumeration that returns 30 pairings is a perf bug.

### Where alternatives actually come from

Probed against the live implementation (2026-07-05), realistic
name pairs produce **1–3 pairings** in single-digit microseconds.
The alternatives observed have exactly three sources:

1. **Cross-category tags on the same tokens** — "john" carrying
   both `NICK:JACK` and `NAME:Q104552334`; "bin" carrying both
   `NAME:Q104253346` and `SYMBOL:BIN`. These are scoring-distinct
   (different SYM_SCORES/SYM_WEIGHTS rows) and *must* surface as
   separate pairings; only NK can rank them.
2. **Overlapping spans** (compound vs constituent, "PLA" vs
   "PLA China") — mostly resolved before enumeration by the
   widest-first binder and the subsumption prune.
3. **Repeated symbols cross-binding** (two "bin" tokens on each
   side) — collapsed by the `(qmask, rmask, category multiset)`
   equivalence dedup; the category-multiset key correctly
   factorizes (NAME,SYMBOL) ≡ (SYMBOL,NAME).

The 2^E blowup (D1 below) was never inherent in the data; it is an
implementation defect in the skip-branch of the DFS.

### Formal framing

Candidate edges with "conflict = part-mask overlap on either side"
make each pairing a **maximal independent set** in the conflict
graph, deduped by scoring-equivalence class. Two known results
bound the design space:

- A graph on E vertices can have up to 3^(E/3) maximal independent
  sets (Moon–Moser), so *any* exhaustive enumeration needs a budget
  against adversarial input — no clever algorithm removes the cap,
  it only moves where it binds.
- Maximal independent sets factorize over connected components of
  the conflict graph. In the common case (few or no conflicts)
  component decomposition makes enumeration linear in E; genuine
  alternatives live inside small components.
- The equivalence-class dedup key does **not** fully factorize
  (corpus-verified, 9/814 cases): when two components each offer a
  category choice on identical masks, the global category
  *multiset* collapses cross-component swaps — (NAME, SYMBOL) ≡
  (SYMBOL, NAME) — that per-component dedup keeps apart. The
  product over components is a superset of the current output; a
  final global-key dedup over the (capped, small) product restores
  exact parity.

If per-category scores were available in rigour, "best pairing"
would be maximum-weight set packing (NP-hard in general, trivial at
this size) — but per the ratio/residue coupling above, even that
wouldn't yield the true argmax. Enumeration-with-caps is the right
shape; the caps need justification, not avoidance.

## Requirements

Functional — traced to consumer code:

- **R1 (purpose)** Bind the parts of two names that shared symbol
  evidence explains into disjoint `Alignment`s, so the matcher can
  price symbol evidence per category and hand only the residue to
  string distance.
- **R2 (alternatives)** Where evidence is ambiguous in a way that
  can change the downstream score — different category multiset or
  different coverage on the same input — emit each option as a
  separate pairing. Collapse scoring-equivalent selections: one
  pairing per `(qmask, rmask, sorted category multiset)` class.
- **R3 (maximality / commit-to-evidence)** Every emitted selection
  is maximal — no un-picked edge is compatible with it. The empty
  pairing `[()]` is emitted **only** when there are no candidate
  edges at all (guard trips, no spans, no shared symbols); once any
  symbol evidence exists we commit to it and never offer a
  no-symbols alternative that would compete in scoring (deliberate
  NK-compatible semantics, commit ac23f7d). Callers rely on the
  returned list being non-empty.
- **R4 (binding semantics)** A symbol occurring N times on one side
  and M on the other yields min(N, M) edges (instances are
  interchangeable for scoring), bound widest-first. Compatibility
  filters are applied before an edge exists: INITIAL requires a
  single-char side; NAME/NICK require pairwise
  `NamePartTag::can_match` across the two spans. These are matcher
  policy embedded in the binder — any new pipeline must apply them
  at the same point.
- **R5 (object identity)** Output alignments must reference the
  input names' actual `NamePart` objects (NK computes remainders by
  set membership, `match.py:57-60`) and reuse interned `Py<Symbol>`
  objects; `score`/`weight` ship as 1.0 placeholders that NK
  mutates in place (see arch-name-pipeline.md § Alignment).
- **R6 (output order is semantics)** NK keeps the *first* pairing
  that attains the max (`if score > retval.score`, strict) and
  builds the explain-detail from it; it also early-exits at 1.0.
  Output order therefore affects results and should be
  deterministic and best-first-ish (higher coverage first).

Non-functional:

- **R7 (bounded cost)** Input is externally supplied (yente
  queries). Worst-case must be hard-bounded — polynomial pipeline
  plus explicit budgets on enumeration and on emitted pairings.
  Typical case stays in single-digit microseconds. Never hold the
  GIL for unbounded work.
- **R8 (determinism)** Same input → same output, bitwise, run to
  run and process to process — xref reproducibility, explain-detail
  stability, test stability. No HashMap iteration order may reach
  the output. (Currently violated; see D2.)
- **R9 (upstream contract)** Pairing assumes every part occurrence
  carries its spans (violated by D3) and that symbol ids don't
  collide across distinct identities (violated for NUMERIC, D4).
  The rework's tests must not bake in either broken behavior.

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

## Approaches considered

### A — conflict-component decomposition + budgets (chosen)

Keep the interface and output contract; replace the enumeration.
Factorize maximal-selection enumeration over connected components
of the conflict graph, take isolated edges unconditionally, and cap
both per-component alternatives and total emitted pairings.

Preserves R1–R6 exactly below the caps; the caps themselves are the
only semantic change and only bind on adversarial input (R7). No
interface churn in either repo. Detailed in the sketch below.

### B — pass the category score/weight table into rigour (deferred)

Accept a `SYM_SCORES`/`SYM_WEIGHTS`-shaped table as a config
parameter (policy stays authored in NK; rigour just receives
numbers, as `CompareConfig` already does for the residue budget).
That would let rigour rank pairings best-first by a partial score
bound and make truncation principled instead of coverage-heuristic.

Rejected for this rework: it cannot make selection *exact* (the
ratio objective and global residue still couple components), so it
buys only a better ordering — and a coverage-desc heuristic order
gets most of that for free. Requires coordinated changes in two
repos. Worth revisiting if corpus data shows the truncation cap
binding on real names.

### C — return the conflict structure, let NK compose (rejected)

Return forced edges plus per-component alternative lists and let NK
take the cartesian product where its scoring lives. Avoids the
product blowup inside rigour — but NK's objective is a global ratio
over a global residue, so NK would have to reassemble full pairings
anyway to score them; the product (and its cap) just moves across
the FFI boundary, now paid in Python. Interface churn in two repos
for negative gain.

### D — single greedy pairing (rejected)

Return one maximal selection chosen by fixed category priority.
O(E log E), trivially deterministic, minimal output. But the probe
shows real names where the argmax depends on the alternative set:
"john"↔"john" as `NICK` (0.6·0.8) vs `NAME` (0.9·1.0) are different
scores, and picking between them in rigour means hard-coding
matcher policy here. Loses R2 outright.

### Considered and rejected: harder token (part-count) caps

A lower `MAX_PARTS` looks like a cheap safety lever but is neither
sufficient nor necessary here. Not sufficient: D1's blowup is in
edge count and conflict structure, not part count — tokens bound
edges only loosely (several symbols per token, overlapping spans
chaining into large components), so even 16-part names admit
adversarial enumeration without budgets; with the budgets in
place, the worst case is already bounded and a part cap adds no
guarantee. Not free: the guard trips silently per name (D5),
losing *all* symbol evidence, and real names live near any lower
line — full Russian legal forms run 8–12 tokens, Arabic bin/al
chains and dirty registry name fields run longer, and those are
exactly the names symbol pairing helps most. Keep 64 as the
bitmask-width guard.

Two adjacent ideas that *do* have merit, recorded separately:

- **Post-dedupe edge cap** (e.g. top 64 edges by coverage
  popcount, deterministic tie-break): bounds the conflict graph,
  components, and enumeration input directly, degrading by
  dropping the weakest evidence instead of all of it. Cheap
  belt-and-braces alongside the enumeration budgets.
- **Pipeline-level token limit** ("> N tokens is junk / truncate")
  would bound the costs that genuinely scale with part count —
  `compare_parts`' O(P_q·P_r) DP per emitted pairing and the
  `names_product` loop — but that's matcher policy / data hygiene
  for nomenklatura or `analyze_names` ingestion, not a pairing
  lever; needs a corpus token-count distribution first.

### E — fold `match_name_symbolic` into rigour (out of scope)

The residue DP (`compare_parts`) already lives in rigour; if the
category tables and policy passes moved too, pairing selection
could become an internal branch-and-bound with real score bounds —
no enumeration surfaced at all, and the pairings-cap question
dissolves. That's an architectural move across the rigour/NK
boundary with its own plan-sized blast radius (config surface,
explain-detail generation, `weight_extra_match` needs `Name`
context). Noted as the long-term direction that would make this
whole contract internal; not this rework.

## Rework sketch (approach A)

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
   component (no cross-component conflicts by construction). So:
   enumerate maximal selections per component (DFS is fine here —
   components are where genuine alternatives live), dedupe per
   component, take the cartesian product across components, then
   **dedupe the product by the global `(qmask, rmask, category
   multiset)` key**. The final pass is required for parity: the
   global key collapses cross-component category swaps on
   identical masks that per-component dedup keeps apart (see
   Formal framing; 9/814 corpus cases).
4. **Budget the product.** The product can still explode when many
   components each carry alternatives. Cap total emitted pairings
   (proposal: 32) and per-component alternatives (proposal: 8),
   truncating deterministically after sorting alternatives by a
   stable key (coverage popcount desc, then masks) — which also
   satisfies R6's best-first-ish ordering and feeds NK's
   `score == 1.0` early exit. When a single component's own
   enumeration exceeds an iteration budget, degrade to its greedy
   maximal selection rather than hanging. Truncation is a behavior
   change vs "all equivalence classes" — acceptable because
   downstream scores every pairing and takes a max; dropping
   low-coverage alternatives beyond a bound is exactly what a
   consumer would do anyway. Document the cap in the docstring.
5. **Determinism.** Fix `edge_sort_key` to `(qmask, rmask,
   category, id)` (D2); sort component lists and alternatives with
   full-mask keys; no HashMap iteration order may reach the output
   (R8).
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
- Corpus probe (run 2026-07-05 over
  `nomenklatura/contrib/name_bench/cases.csv`, 826 curated
  match/non-match pairs, 814 pair_symbols calls after dropping
  Vessel rows; edge/component structure reconstructed from emitted
  alignments):
  - pairings per call: 87.3% → 1, 10.7% → 2, max **6** (Arabic
    bin/ben chains with two cross-category components);
  - deduped edge unions ≤ 9; conflict components ≤ 3 edges,
    ≤ 3 alternatives; parts per name ≤ 10;
  - mean 4.9µs/call, zero calls over 1ms;
  - 9 factorization mismatches — the finding folded into sketch
    step 3 (global dedup pass after the product).
  Conclusion: the proposed caps (32 pairings / 8 per component)
  sit 5×+ above anything real data produces — they are purely
  adversarial-input guards and can even be tightened. Caveat: this
  corpus is curated and benign (max 10 parts/name); it validates
  that caps won't bind on real names, not the adversarial tail,
  which the perf tests cover separately. It also doesn't answer
  the R3 commit-to-evidence question — that needs scoring, i.e.
  running NK's `match_name_symbolic` with and without the
  symbol-free alternative.
- D3 fix verified via `analyze_names(PER, ["A A Milne"],
  infer_initials=True)` — both initial parts must carry spans, and
  pairing against "Alan Alexander Milne" must align both.

## Open questions

- Cap values: the name_bench probe (see Verification) shows real
  maxima of 6 pairings / 3 alternatives per component, so 32 / 8
  are comfortably above the data. Remaining question is only
  whether to confirm against a broader xref corpus (name_bench is
  curated) before freezing the numbers in the docstring.
- On budget overflow: degrade to greedy-per-component (proposed)
  or fall back to `[()]`? Greedy keeps symbol evidence, which
  matches the commit-to-evidence contract (R3) better.
- Whether D3 lands inside this rework or as its own change —
  it alters pairing outputs on its own, so sequencing matters for
  the parity harness (fix D3 first, re-baseline, then rework).
- R3's commit-to-evidence semantics: worth a one-time corpus check
  that never offering the "ignore this symbol" alternative doesn't
  suppress scores where a low-weight symbol edge (e.g. SYMBOL at
  weight 0.3) displaces a residue cluster that would have scored
  1.0 at weight 1.0. If it does, that's a contract discussion with
  NK, not a pairing implementation detail.
