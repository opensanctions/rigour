---
description: Port the symbol-pairing generation out of nomenklatura's name matcher into rigour. Design doc + algorithmic rework — current Python impl generates too many pairings. Lands as `rigour.names.symbol.pair_symbols`; Rust port follows the Python API.
date: 2026-04-22
tags: [rigour, nomenklatura, rust, names, pairings, performance, matching]
status: landed (April 2026) — Rust core + Python wrapper in place, 21 pytest + 11 cargo tests green
---

# Symbol pairing in rigour — `pair_symbols`

## Motivation

`generate_symbol_pairings` in
`nomenklatura/matching/logic_v2/names/match.py` consumes roughly
**10% of profiled name-matching time** on a representative workload.
The replacement lands as `rigour.names.symbol.pair_symbols`,
pulling the alignment logic into rigour so it can be Rust-backed
alongside `Name` / `NamePart` / `Span` / `Symbol`.
It builds the set of non-overlapping alignments between the symbol
spans of a query name and a candidate name — the cheap short-cut
that lets the downstream Levenshtein pipeline skip whole runs of
parts that have already been explained by a shared symbol annotation.

Two problems motivate the port:

1. **Combinatorial growth.** The current algorithm walks query
   parts, extending a growing list of pairings by every compatible
   `(query_span, result_span)` candidate. In the pathological case
   a single shared symbol with N matches on each side blows the
   pairing list up by a factor of N per query-part visit. The
   `seen: Set[int]` dedup-on-hash is a patch on a patch — it
   globally blacklists a `(qparts, rparts, category)` key after
   its first successful use, which both over-prunes (later
   pairings never get a chance at the same edge) and under-prunes
   (distinct pairings with identical coverage are still emitted).

2. **Downstream over-scoring.** `match_name_symbolic` then scores
   every generated pairing independently. Pairings that share the
   same `(query_used, result_used)` coverage and the same multiset
   of symbol categories produce **identical scores** — because
   `SYM_SCORES` / `SYM_WEIGHTS` key only on category, and the
   literal-equality score override keys only on `part.comparable`.
   The extra pairings are wasted work.

The new algorithm uses three collapse levers to get from
"exponential in binding permutations" down to "one pairing per
materially distinct coverage":

- **Intra-symbol greedy binding** — N-times-on-one-side,
  M-times-on-the-other collapses to `min(N, M)` deterministic
  edges, not N × M enumeration.
- **Same-category subsumption** — a compound edge
  (`NAME:QvanDijk`) eats the shorter same-category edges
  (`NAME:Qvan`, `NAME:QDijk`) it dominates.
- **Coverage-class dedup** — the DFS memoises
  `(qmask, rmask, sorted categories)` so only materially distinct
  coverings survive.

## Scope

- **In scope.** New `pair_symbols` function in
  `rigour.names.symbol` (Python surface) backed by
  `rust/src/names/pairing.rs` (via `rigour._core.pair_symbols`).
  The `Pairing` class in nomenklatura is retired — it has no
  rigour-side analogue; alignments are returned as
  `list[tuple[SymbolEdge, ...]]`.
- **Out of scope.** `match_name_symbolic` stays in Python. The
  `Match` class stays in Python (nomenklatura-owned).
  `weighted_edit_similarity`, `align_person_name_order`, and the
  magic.py scoring stay in Python. No change to the `Name` /
  `NamePart` / `Span` / `Symbol` rigour object graph.

## Boundary and data types

The public Python API lives in `rigour.names.symbol` and returns
rigour-native types — nomenklatura's `Match` / `Pairing` are
hydrated on the caller side from these.

```python
from rigour.names.symbol import pair_symbols, SymbolEdge

# In rigour/names/symbol.py:
@dataclass(frozen=True)
class SymbolEdge:
    query_parts: tuple[NamePart, ...]  # references into query.parts
    result_parts: tuple[NamePart, ...]  # references into result.parts
    symbol: Symbol                      # shared Symbol (same both sides)

def pair_symbols(
    query: Name, result: Name
) -> list[tuple[SymbolEdge, ...]]: ...
```

Each returned pairing is a tuple of edges (frozen so it's
hashable). The list always starts with the empty pairing `()` so
callers have a guaranteed fallback. `query_used` / `result_used`
are not returned — they're the union of `query_parts` /
`result_parts` over the edges and trivial to compute caller-side.

### Rust-side representation

The Rust layer returns the same shape in primitive terms. Part
indices into `Name.parts` plus a Symbol reference per edge; the
`#[pyclass]` wrapper binds the indices back to `Py<NamePart>`
references:

```
struct PairedEdge {
    query_parts: Vec<u32>,   // indices into query.parts
    result_parts: Vec<u32>,  // indices into result.parts
    symbol: Py<Symbol>,      // Arc-interned, cheap to clone
}
```

**No `Span` in the output.** `Span` objects are scaffolding the
algorithm only reads during edge construction — once candidate
edges exist, the DFS works on `(qmask, rmask, category)` tuples
alone. Threading span identity through to the output would add a
dependency on `Name.spans` index stability we don't need;
`Name.parts` is a frozen tuple with a stable contract, `Name.spans`
is a growable list the tagger appends to.

### Nomenklatura-side hydration

`match_name_symbolic` consumes `list[tuple[SymbolEdge, ...]]` and
builds `Match` objects from each edge:

```python
Match(
    qps=list(edge.query_parts),
    rps=list(edge.result_parts),
    symbol=edge.symbol,
    score=SYM_SCORES.get(edge.symbol.category, 1.0),
    weight=SYM_WEIGHTS.get(edge.symbol.category, 1.0),
)
```

`query_used` / `result_used` (previously `Pairing` fields) become
local variables computed from the edge list. The `Pairing` class
in nomenklatura is retired. The details of that migration are
tracked as follow-up work (see *Nomenklatura-side changes*).

## Invariants we exploit

These are the observations that let the Rust side be more compact
than a literal port. Each one is derived from reading the current
scoring pipeline in `match.py` and `magic.py`; treat them as
preconditions the port relies on, not as aspirations.

1. **Score is category-driven.** `SYM_SCORES` and `SYM_WEIGHTS` in
   `magic.py` are keyed on `Symbol.Category` alone. Two pairings
   that differ only in *which* symbol within the same category
   covers a given part pair score identically. "John" tagged as
   `NAME:QAAA` vs. `NAME:QBBB` is a distinction without a
   downstream difference — unless the parts themselves differ,
   which they don't if the coverage is the same.

2. **Literal equality is a coverage property.** The `match.score
   = 1.0` upgrade in `match_name_symbolic` fires when the paired
   parts are pairwise `comparable`-equal. It depends only on the
   parts, not on which symbol paired them.

3. **Remainder scoring is a function of coverage.** The `query_rem`
   / `result_rem` lists are computed from `query_used` /
   `result_used`. Two pairings with the same coverage have the
   same remainders and therefore the same `weighted_edit_similarity`
   output.

4. **Family-name boost is a coverage property.** `Match.is_family_name()`
   walks the match parts' `tag` field. Symbol-agnostic.

Conclusion: **pairings with equal `(query_used, result_used,
category_multiset)` score identically downstream.** The Rust side
emits at most one pairing per equivalence class, and in the common
case returns a single best pairing.

Important: we **must** preserve distinct coverage classes that
arise from *different-symbol* choices. Two pairings with different
`query_used` sets hit `weighted_edit_similarity` on different
remainders and can score differently. The port isn't allowed to
collapse those.

### Intra-symbol binding is not enumerated

When a single symbol occurs N times on one side and M times on the
other, the algorithm binds `min(N, M)` edges inside **one** pairing.
It does not emit N × M alternative pairings for the different
assignments of instances to each other.

Rationale: within a symbol, instances are interchangeable for
scoring. `NAME:QJohn` on the first `john` vs. `NAME:QJohn` on the
second `john` yields the same `comparable` on the part side and
the same category on the edge side; downstream scoring can't
distinguish them. Enumerating the assignments would produce
pairings that are by construction score-equivalent.

Worked cases:

- **Symmetric** ("John John Smith" vs "John John Smith", 2 on both
  sides): one pairing with **two** John edges and one Smith edge.
  Full coverage on both sides.
- **Asymmetric** ("John Smith" vs "John John Smith", 1 vs 2): one
  pairing with **one** John edge and one Smith edge. One result-side
  John remains unaligned and lands in the downstream remainder.
- **Asymmetric on query side** ("abd al-kadir abdel-kader husseini"
  vs "abdelkader husseini", 2 query-side Qkader spans vs 1
  result-side): one pairing with one Qkader edge (bound to
  whichever qspan the algorithm picks) + one husseini edge. The
  other qspan is unaligned.

This is a **strong collapse** relative to the Python implementation,
which emitted one pairing per possible binding. The Python tests
in `tests/matching/test_symbol_pairings.py` that asserted exact
pairing counts on asymmetric cases (e.g.
`test_multiple_result_spans_for_same_symbol`, which expects 2 for
"John" vs "John Johnny") will need updating when the port lands.

Multiple pairings still arise when **distinct categories** create
genuinely different coverings. The canonical case: a single token
carries symbols from more than one category, and both categories
also appear on the other side.

Worked example — `"van Putin"` on both sides. Dutch nobiliary
"van" lives in two corpora: the person-names corpus as `NAME:Qvan`
and the generic-qualifier list as `SYMBOL:van`. The candidate-edge
set for the van tokens contains two edges with identical
`(qmask, rmask)` but different symbols. They can't both be
selected in one pairing — their qmasks/rmasks conflict — so two
coverings surface:

- Pairing A: `{van↔van NAME, putin↔putin NAME}`
- Pairing B: `{van↔van SYMBOL, putin↔putin NAME}`

Downstream scoring weighs the two differently (SYM_SCORES[NAME]
vs SYM_SCORES[SYMBOL], SYM_WEIGHTS[NAME]=1.0 vs SYM_WEIGHTS[SYMBOL]=0.3),
so the Python side needs to see both and pick the better. The DFS
dedup key is `(qmask, rmask, sorted categories)` — same masks,
different categories → both survive.

The example uses `"van Putin"` (not a stored compound) deliberately.
Real inputs like `"Jan van Dijk"` trigger the same-category
subsumption rule (step 2 of the algorithm): `NAME:QvanDijk`
covering `[van, Dijk]` absorbs the shorter `NAME:Qvan` and
`NAME:QDijk` edges in the same category; `SYMBOL:van` (different
category) survives unchanged.

The same shape applies to **NAME vs NICK** overlaps (a token that
has both a canonical-name symbol and a nickname symbol to the
same referent) and **NAME vs INITIAL** overlaps when the query's
single-letter part also carries a full-name symbol.

## Algorithm

### Shape

Three phases, all Rust-side, no FFI between phases:

1. **Build candidate edges per symbol.** For each shared `Symbol`
   (same category *and* same id) with qspans `Q` and rspans `R`,
   bind `min(|Q|, |R|)` non-conflicting edges within this symbol
   alone. Per-edge compatibility filters:
   - `INITIAL`: reject if both sides' first part is > 1 char.
   - `NAME` / `NICK`: reject if any `(qp, rp)` in the **cartesian
     product** of qspan.parts × rspan.parts fails
     `qp.tag.can_match(rp.tag)`. This deviates from the pre-port
     Python, which used `zip(qparts, rparts)` and silently ignored
     parts beyond the shorter side on unequal-length spans — that
     was a latent bug, not a semantic choice we're preserving.

   Intra-symbol binding is greedy by lexicographic
   `(qspan_idx, rspan_idx)` — for each qspan in span-index order,
   take the first unbound rspan (in span-index order) that passes
   the compatibility filter. Span indices follow `Name.spans`
   order, which is itself the order the tagger emitted the spans
   (first-token-position ascending). No enumeration across
   alternative bindings within a symbol.
   Store each survivor as a primitive record. This is the only
   place Span objects are touched — after this pass the DFS works
   on masks and the carried `Py<Symbol>`:
   ```
   struct Edge {
       qmask: u64,           // bitmask of query part indices covered
       rmask: u64,           // bitmask of result part indices covered
       symbol: Py<Symbol>,   // carried through to output edges
       weight: u32,          // == qmask.count_ones() + rmask.count_ones()
   }
   ```
   Names with more than 64 parts short-circuit the whole function
   (see *Very-long-name guard* below); inside this step we can
   treat `u64` as given.

2. **Same-category subsumption prune.** Drop candidate edge `E1`
   whenever another candidate `E2` satisfies:
   - `E1.category == E2.category`
   - `E1.qmask ⊂ E2.qmask` (strict subset)
   - `E1.rmask ⊂ E2.rmask` (strict subset)

   Worked example — `"Jan van Dijk"` on both sides has at least
   three NAME candidates on the `van` / `Dijk` tokens:
   `NAME:Qvan` ↔ `NAME:Qvan` covering `[van]`, `NAME:QDijk` ↔
   `NAME:QDijk` covering `[Dijk]`, and `NAME:QvanDijk` ↔
   `NAME:QvanDijk` covering `[van, Dijk]`. The first two are
   strictly subsumed by the third within the NAME category and
   drop out. `SYMBOL:van` (different category) is kept. The
   emitted pairings after the DFS are:
   - `{Qjan, QvanDijk}` — NAME coverage over all three parts.
   - `{Qjan, SYMBOL:van}` — SYMBOL coverage on van, Dijk unaligned.

   Without this prune, the DFS would also emit `{Qjan, Qvan,
   QDijk}` (three NAME edges) as an extra coverage class — same
   qmask/rmask as `{Qjan, QvanDijk}` but with a `{NAME, NAME, NAME}`
   multiset instead of `{NAME, NAME}`. We prefer the compound:
   `QvanDijk` is a specific named-entity alias (the compound Dutch
   surname "van Dijk" as one name), so treating it as a single
   match carries more semantic weight than counting `van` and
   `Dijk` as two independent Wikidata hits on the same token
   range. Coverage is the same either way; the scoring difference
   is small (weighted-average over different edge counts) and
   consistent with the "compound dominates" preference.

   Subsumption operates **across** Symbol ids within a category —
   different Symbol, same category. Within a single Symbol,
   intra-symbol binding already produces disjoint masks, so
   there's nothing to prune.

3. **Enumerate cross-symbol coverage classes.** A selection is a
   set of edges whose qmasks are pairwise disjoint and whose rmasks
   are pairwise disjoint. We want every selection that is
   **coverage-maximal** across symbols (no further edge from the
   candidate set could be added without conflict), *distinct* from
   other selections in either `(qmask, rmask)` or category
   multiset. Intra-symbol alternatives have already been collapsed
   in step 1, so the DFS only branches where different *symbols*
   compete for the same parts.

   Approach: backtracking DFS over edges in a canonical order
   (sorted by `(weight desc, qspan_idx asc, rspan_idx asc)`),
   with two dedup caps:
   - **Lexicographic prune.** Only consider edges with index ≥
     the last-picked edge index. Eliminates permutation duplicates.
   - **Coverage dedup.** Memoise visited `(qmask, rmask,
     category_multiset)` triples in a `HashSet`. Skip any selection
     whose final coverage is already known.

   In the common case (no cross-category overlap on the same
   parts) this produces exactly one selection — the greedy
   longest-first assignment — in O(E) time. The DFS only branches
   when two candidate edges with **different categories** cover
   the same parts (e.g. `NAME:Qvan` and `SYMBOL:van` on the same
   token). Multiple rspan candidates for a single symbol don't
   branch the DFS — they're collapsed in step 1 by greedy
   intra-symbol binding.

4. **Emit paired-edge records.** Convert each surviving selection
   into a `Vec<PairedEdge>`. The empty selection (no edges chosen)
   is always emitted as the first element — the fallback the
   Python-side scoring loop uses when no symbol coverage wins
   outright.

### Why not max-weight bipartite matching

A classic bipartite-matching solver (Hungarian, max-flow) would
find *one* optimal assignment, not the equivalence class set we
need. Downstream scoring isn't monotone in pairing weight: adding
a low-weight `ORG_CLASS` edge can reduce the average score if the
removed remainder pair would have scored better under
`weighted_edit_similarity`. So we need to let the Python side see
the distinct coverages and pick the best post-hoc.

### Why not greedy-only

Greedy longest-first is the right backbone but loses one case:
cross-category alternatives on the same parts. Query `van Putin`
vs. result `van Putin` where `van` carries both `NAME:Qvan` and
`SYMBOL:van`: greedy picks one (say, the higher-weight category)
and discards the other. The coverage DFS keeps both selections —
same qmask/rmask, different categories — because their downstream
scores genuinely differ under `SYM_SCORES[NAME]=0.9, W=1.0` vs.
`SYM_SCORES[SYMBOL]=0.9, W=0.3`. Python-side scoring picks the
best.

Whether keeping both materially shifts final scores in production
is an empirical question — see *Deferred: collapse to single
pairing?*.

### Complexity

- Candidate edges: O(|Qspans| × avg-rspans-per-symbol). The symbol
  hash map keeps this close to linear.
- Subsumption prune: O(E²) over a low-dozen edge count — trivial.
- DFS with coverage dedup: worst case exponential in the number
  of cross-category ambiguity points (edges with same masks but
  different categories), bounded in practice because each branch
  must produce a distinct `(qmask, rmask, categories)` triple and
  the mask space is at most 2^parts. Intra-symbol alternatives
  and same-category redundancy are collapsed before the DFS runs,
  so the actual branching surface is small.
- Expected pairing count per call: 1 in the common case, 2–3 when
  cross-category overlaps fire (e.g. a `van`-like token carrying
  both NAME and SYMBOL).

### Very-long-name guard

If either name has more than 64 parts, we refuse to compute
pairings and return `[()]` (just the empty fallback). Names that
large are almost always data errors (conglomerated legal-name
blobs), and blowing past the `u64` bitmask path would impose a
`Vec<u64>` fallback whose cost is unjustified for inputs this
degenerate. Downstream scoring falls back on pure remainder
comparison in that case.

### Edge output order

Edges inside a pairing are emitted in `(qmin_idx, rmin_idx)`
order — deterministic and easy to debug. Callers that need a
different canonical order sort themselves; the `pair_shape`
test helper does exactly that.

## API

Rust side (`rust/src/names/pairing.rs`):

```rust
pub fn pair_symbols(
    py: Python<'_>,
    query: &Name,
    result: &Name,
) -> PyResult<Vec<Vec<PairedEdge>>>;
```

PyO3 exposure: `rigour._core.pair_symbols(query, result) ->
list[tuple[SymbolEdge, ...]]`. The Python wrapper in
`rigour/names/symbol.py` is a thin pass-through that constructs
`SymbolEdge` dataclass instances from the PyO3 output.

Until the Rust side lands, `rigour.names.symbol.pair_symbols` is
a stub that raises `NotImplementedError`. This lets the test file
at `tests/names/test_symbol.py` import cleanly; tests fail with
the stub's message until the implementation arrives.

## Tests

The rigour-side spec lives in `tests/names/test_symbol.py` — 21
tests exercising `pair_symbols` with real `analyze_names` outputs
so the tagger corpus drives the inputs. Uses a `pair_shape` helper
that normalises each pairing to a sorted `list` of
`(query_text, result_text, category)` tuples — sorted so
assertions are order-free, list (not set) so multiplicity is
preserved for cases like "two identical edges inside one pairing".
Coverage groups:

- **Degenerate inputs.** No shared symbols → single empty pairing;
  neither name carries any symbol at all → single empty pairing
  (so downstream full-name Levenshtein still runs); empty query
  `Name` against a populated result → single empty pairing.
- **Person names, happy path.** Identical; reordered; partial
  overlap (unmatched tokens land in the remainder, not in edges);
  INITIAL ↔ full given-name pairing; INITIAL rejected when both
  sides are multi-char; NAME-edge rejection via `NamePartTag.can_match`
  when part tags are incompatible.
- **Multi-part alignment.** `abd al-kadir` (3 parts) vs `abdelkader`
  (1 part) for the same NAME symbol; the same NAME symbol appearing
  twice on one side and once on the other (one pairing, one edge
  bound, the extra instance unaligned); twice on both sides (one
  pairing with two edges).
- **Ambiguity on the result side.** Query `John` vs result
  `John Johnny` where both result parts carry the same NAME symbol
  → one pairing with one edge, one result part unaligned.
- **Cross-category on the same part.** `van Putin` on both sides —
  `van` carries both NAME and SYMBOL, so two pairings surface:
  one uses the NAME edge for van↔van, the other uses the SYMBOL
  edge. Same coverage, distinct categories → distinct downstream
  scores. Uses an invented compound to keep the compound
  subsumption rule out of the picture.
- **Same-category subsumption.** `Jan van Dijk` on both sides —
  the compound `NAME:QvanDijk` edge subsumes the shorter `NAME:Qvan`
  and `NAME:QDijk` within the NAME category (pruned before the
  DFS), but `SYMBOL:van` survives (different category).
- **Org-class cases.** Abbreviation vs long form after
  `replace_org_types_compare` collapses both (canonical token
  pairs); positional independence (`OOO Garant` vs `Garant LLC`);
  `Stripe Company` vs `Stripe Limited Liability Company` pinning
  that `limited` / `liability` stay out of the pairing edges.
- **Cross-script.** Latin `Vladimir Vladimirovich Putin` vs
  Cyrillic `Владимир Путин` — NAME edges pair across scripts via
  the Wikidata alias corpus; `Vladimirovich` with no counterpart
  stays in the remainder.
- **Structural contracts.** The empty pairing is always first;
  names with more than 64 parts short-circuit to the empty-only
  fallback (guards the `u64` bitmask fast path).

Tests marked `# corpus-dependent` rely on specific tagger corpus
entries — Arabic-name alias sets (`abd al-kadir` ↔ `abdelkader`),
OOO↔LLC synonymy, `John`↔`Johnny`, `van` carrying both NAME and
SYMBOL, `van Dijk` as a compound NAME, Latin↔Cyrillic Putin QIDs.
If the data shifts, the inputs get retuned rather than the
expectations relaxed.

Rust-side `cargo test names::pairing` will cover the pure-Rust
algorithm — edge construction, bitmask dedup, DFS enumeration —
without needing the PyO3 layer.

### Inherited from the pre-port suite

The existing `tests/matching/test_symbol_pairings.py` (in
nomenklatura) stays as a behavioural spec for `match_name_symbolic`
end-to-end. Some of its cases over-specified the *number* of
pairings returned (e.g. `test_multiple_result_spans_for_same_symbol`
asserts exactly 2); those assertions are re-checked once the new
algorithm lands, and if the new algorithm legitimately collapses
equivalent coverings, the test is updated with a callout in the
commit message.

## Implementation outline

### `rust/src/names/pairing.rs`

```rust
struct Edge { qmask, rmask, symbol: Py<Symbol>, weight }
struct PairedEdge { query_parts: Vec<u32>, result_parts: Vec<u32>, symbol: Py<Symbol> }

fn build_candidate_edges(py, query, result) -> Vec<Edge>;
fn prune_subsumed(edges: &mut Vec<Edge>);
fn enumerate_coverage_classes(edges: &[Edge]) -> Vec<Vec<usize>>;
fn to_paired_edges(edges: &[Edge], classes: Vec<Vec<usize>>) -> Vec<Vec<PairedEdge>>;

#[pyfunction]
pub fn py_pair_symbols(
    py: Python<'_>, query: &Name, result: &Name
) -> PyResult<Vec<Vec<PairedEdge>>> {
    // 0. Very-long-name guard — return [()] if either name has > 64 parts.
    // 1. build_candidate_edges
    // 2. prune_subsumed
    // 3. enumerate_coverage_classes
    // 4. to_paired_edges
}
```

Edge construction walks `query.spans` once, groups result spans by
`Symbol` in a `HashMap<Symbol, SmallVec<u32>>` (built once per
call), then forms candidate edges — intra-symbol greedy binding
with per-edge filters (INITIAL multi-char rejection, NAME/NICK
cartesian `can_match`). Rejected edges never enter later stages.

Subsumption prune is O(E²) over the edge list; with typical E in
the low dozens this is trivial. Edges with strictly smaller masks
in the same category as another edge are dropped in place.

Coverage DFS is ~40 lines. Memoisation HashSet keyed on
`(u64, u64, SmallVec<[SymbolCategory; 8]>)` (sorted). Empty
selection always pushed first so the rigour-side contract holds.

### Nomenklatura-side changes

Out of scope for this plan. When rigour ships `pair_symbols`,
nomenklatura's `match_name_symbolic` switches to consume
`list[tuple[SymbolEdge, ...]]` and retires `pairing.py`, but
that's tracked as follow-up work.

## Bench harness

Add `benchmarks/bench_pairings.py` (or equivalent) that runs the
pairing generator over 10k synthetic name pairs drawn from a
template: mix of ORG / PER, varying ambiguity (0, 1, 2 per-part
symbol alternatives), varying length (2–8 parts). Compare wall
time Python-before vs. Rust-after. Expectation is a 10–50× speedup
on the ambiguous cases (FFI + HashMap+regex elimination dominates)
and something modest (~2×) on the trivial cases.

`nomenklatura`'s matcher profile is the ground-truth — re-profile
after the port and confirm the pairing generator's share drops
well below its current 10%.

## Open questions

(None outstanding. Corpus verification closed — all
`# corpus-dependent` tests pass against live tagger output, so
the bets on `Ltd`↔`Limited`, `OOO`↔`LLC`, `abd al-kadir`↔`abdelkader`,
`John`↔`Johnny`, `van` as NAME+SYMBOL, `van Dijk` as a compound,
and Latin↔Cyrillic Putin QIDs are all confirmed.)

### Deferred (revisit after bench harness / profiling)

- **Collapse to single pairing?** Keep multi-pairing output for
  now. Multi-pairings currently arise only from cross-category
  ambiguity (e.g. `van` as NAME vs SYMBOL). A workload study
  could show those rarely swing final scores, in which case we'd
  collapse by picking a canonical category preference. Not worth
  doing speculatively.


### Resolved

- **Where does the module live?** `rigour.names.symbol`.
- **Does `Pairing` (the Python class) survive?** No. `match_name_symbolic`
  hydrates `Match` objects directly from `SymbolEdge` records.
- **Does `Span` cross the FFI boundary?** No. Spans are
  scaffolding used during edge construction only; the output
  carries `NamePart` references + `Symbol`.
- **`can_match` on unequal-length NAME/NICK spans.** Use full
  cartesian product on qspan.parts × rspan.parts, deviating from
  the pre-port `zip`-truncation. The old behaviour was a latent
  bug.
- **Intra-symbol binding determinism.** Greedy lexicographic
  `(qspan_idx, rspan_idx)`; first unbound qspan takes first
  unbound rspan that passes the filter. No measurable perf
  penalty — O(N × M) over a handful of instances per symbol.
- **Edge ordering inside a pairing.** Emitted in
  `(qmin_idx, rmin_idx)` order for determinism.
- **Names with > 64 parts.** Refuse to compute; return `[()]`.
  A `u64` bitmask is the fast path we want to keep; names that
  large are almost always data errors anyway.
- **Same-category subsumption.** Required — edges are pruned
  when a same-category edge strictly dominates both masks. See
  step 2 of the algorithm. Coverage-equivalent; the compound
  match is preferred as the more specific signal.
- **Nomenklatura-side migration.** Out of scope for this plan.
  Tracked separately when rigour ships the Python surface.
