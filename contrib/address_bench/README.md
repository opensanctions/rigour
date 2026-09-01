# address_bench

An evaluation corpus for **address matching**: pairs of full address
strings, labelled for whether they denote the same physical location.

rigour normalizes addresses (`normalize_address`,
`remove_address_keywords`, `shorten_address_keywords`, and the 94
canonical forms in `resources/addresses/forms.yml`) but does not compare
them. The comparison that consumes all of that lives downstream in
`nomenklatura.matching.compare.addresses`, where it carries a feature
weight of 0.98 and is covered by five assertions. This corpus exists so
that a change to either side can be measured.

`cases.csv` is the deliverable and the canonical record. It is
hand-editable: correct a label in place and it survives regeneration.

## Schema

```
case_group,addr1,addr2,is_match,quality,category,notes
```

| column | meaning |
|---|---|
| `case_group` | the stratum the pair was drawn from; doubles as provenance |
| `addr1`, `addr2` | the two address strings, verbatim from source data |
| `is_match` | `true` / `false` — do these denote the same physical location |
| `quality` | `STRONG` / `MEDIUM` / `WEAK` — strength of evidence, applied symmetrically to both labels |
| `category` | free-form slug for slicing: `translit_cyrillic`, `house_number_differs`, `subset`, … |
| `notes` | the adjudicator's one-line reason, plus the source datasets |

There is no `case_id` column. It is derived —
`blake2b(f"{case_group}|{addr1}|{addr2}", digest_size=4)` — so rows stay
hand-editable and can be inserted anywhere.

`quality` is about how confidently the pair can be labelled at all, not
about how hard it is to match. `WEAK` marks the rows where a reasonable
person could disagree; a scorer that fails them is not obviously wrong,
while a scorer that fails `STRONG` rows is.

### The `subset` case

`MARYVILLE, TN 37804` and `2651 SEVIERVILLE ROAD, MARYVILLE, TN 37804`
are consistent, but one is strictly less specific. These land as
`is_match=true, quality=WEAK, category=subset`. Downstream behaviour
here is a policy choice, not a fact — `nomenklatura`'s `_address_match`
currently short-circuits any subset relation to 1.0 — so the corpus
records the relation and declines to be emphatic about it.

## Strata

Pairs come from the OpenSanctions statements dump, restricted to full
address strings (`prop IN ('address', 'full')`) — never the structured
`street` / `city` / `postalCode` parts of an `Address` entity.

| `case_group` | how the pair was found | prior |
|---|---|---|
| `same_entity_xds` | one entity, two source datasets | usually the same address, rendered differently |
| `same_entity_1ds` | one entity, one source dataset | mixed: CJK original vs English translation, but also genuine multi-site records |
| `block_postcode` | different entities, shared postcode, token Jaccard 0.3–0.75, street-level detail on both sides | usually different — same city, different street or house number |
| `block_gap` | different entities, shared postcode, Jaccard 0.75–1.0 | genuinely mixed — one component apart |
| `block_raretoken` | different entities, **no postcode on either side**, sharing an uncommon token, Jaccard ≥ 0.4 | genuinely mixed |
| `block_neardupe` | different entities, identical token set, different rendering | over-generated and harvested, see below |
| `control_same` | identical after casefolding and stripping punctuation | floor |
| `control_unrelated` | no shared tokens at all | ceiling |

**The stratum is a prior, not a label.** Every pair is adjudicated
individually, because none of these heuristics is reliable:

- One entity can hold two real addresses — a registered office and a
  factory, or two branches of one bank.
- One dataset can hold both an original and a translation of a single
  address.
- Two unrelated companies routinely share a registered-agent address.

`block_gap` fills the seam between `block_postcode`, which stops at 0.75,
and `block_neardupe`, which starts at token-identical. Strings in that
band differ in exactly one component — a unit, a house number, a
building name — which is the hardest call in the corpus and where a
token-overlap scorer does most of its damage.

`block_raretoken` exists because a quarter of usable address strings
(165,328 of 678,274) carry no postcode-like token, so both other block
strata are blind to them. Blocking instead on a token that appears in
between 2 and 40 of those addresses reaches them. The payoff is source
coverage rather than script coverage: the stratum draws on international
sanctions lists (`tw_shtc`, `ch_seco_sanctions`, `eu_fsf`,
`fr_tresor_gels_avoir`) instead of US medical-exclusion registries, and
brings in sixteen datasets that appear nowhere else in the block strata
— Brazil, Georgia, Moldova, Indonesia, Israel, Canada. Note that the
addresses themselves are mostly *romanised* rather than in local script,
so this widens geographic reach, not the script mix.

`block_neardupe` is generated at roughly ten times the size it
contributes. Pairs with identical token sets are ~96% the same address
written two ways, which are cheap rows; the remaining few percent are
the most valuable rows in the corpus, because their token sets *collide
exactly* while the addresses differ:

```
УЛ. ВАРШАВСКОЕ Д.17 СТР.1        УЛ. 1-Я МАГИСТРАЛЬНАЯ Д. 17/1 СТР. 1
Ш  ВАРШАВСКОЕ Д. 1 СТР. 17       УЛ. 1-Я МАГИСТРАЛЬНАЯ Д. 17   СТР. 1

Virginia, West Virginia, US      ПЕР. Б. ТРЁХСВЯТИТЕЛЬСКИЙ Д. 2/1 СТР. 1
West Virginia, Virginia, US      ПЕР. Б. ТРЁХСВЯТИТЕЛЬСКИЙ Д. 2/1 СТР. 2
```

House and structure numbers transposed, order-swapped state names,
building-letter suffixes. Nothing that scores token overlap can ever
separate these — they are guaranteed false positives at 1.0 — so they
are worth classifying ten thousand ordinary pairs to find. `adjudicate.py`
keeps every non-match and caps the matches (`HARVEST_MATCH_CAP`);
discarded rows stay in the verdict cache, so raising the cap later costs
nothing.

`block_postcode` requires at least six tokens on both sides. Without
that it fills with city-and-postcode strings paired against full
addresses, which is a subset relation rather than the hard negative the
stratum exists to supply — and the same-entity strata already surface
subsets in their natural proportion.

Two skews the generator corrects for: `us_hhs_exclusions +
us_sam_exclusions` alone supplies 71.5k of the 169k same-entity
cross-dataset pairs, and the high-overlap cross-entity blocks are almost
entirely Cyrillic. `generate.py` caps any dataset pair at 40 rows per
stratum and any script bucket at 35% of a stratum. Two strata override the
dataset cap: `block_neardupe`, where the cap only starves the harvest
since few of its rows reach the corpus, and `block_postcode`, the main
source of non-matches, which runs out of distinct pairs before it runs
out of useful ones.

One address pair can reach a stratum by several routes — two dataset
combinations for the same strings, or two different shared rare tokens.
`generate.py` admits each pair once, and `adjudicate.py` will not write
a `case_id` the corpus already holds. The script quota is a
preference, not a hard ceiling: when a stratum's pool cannot fill its
target under the quota, a second relaxed pass tops it up. A stratum
drawn from a single-script population is therefore allowed to stay that
way rather than come up short.

## Evaluating

`make evaluate SCORER=nomenklatura` (or `ftm`) runs a scorer over every
pair in `cases.csv` and reports AUC, accuracy at the best fixed
threshold, per-quality and per-category slices, and the worst
individual failures. The scorers in `evaluate.py` are local
reimplementations of the downstream comparison logic over raw string
pairs, so the bench has no dependency on nomenklatura or
followthemoney.

## Regenerating

Two stages. Neither overwrites `cases.csv`; the second appends only rows
whose derived `case_id` is not already present.

```bash
make candidates STATEMENTS=~/Data/statements-apr26.csv   # -> candidates.csv
make sample                                              # 50 rows, read them
make adjudicate                                          # -> cases.csv
make stats
```

Generation takes about five seconds against the 11 GB dump. Two things
keep it there, and both are load-bearing:

- Pairs are enumerated only within a random sample of postcode blocks,
  and only after the block-restricted rows are materialised. Left to
  itself DuckDB self-joins the full 522k-row table before applying the
  block filter, which costs over an hour of CPU for the same result.
- `block_neardupe` matches on a token-set key, so it is a hash join
  rather than a pairwise sweep.

The normalization keys use Unicode-aware character classes. An ASCII
class erases every Cyrillic, Greek, Han and Georgian address down to its
digits and collapses them onto a single empty key, which silently drops
those pairs from the same-entity strata and makes every pair of them
look identical to the others.

`make sample` is the gate. Read all fifty by hand before spending the
full run; if the labels or reasons look wrong, fix the prompt in
`adjudicate.py`, bump `PROMPT_VERSION`, and re-run.

`adjudicate.py` needs `ANTHROPIC_API_KEY` in the environment. Verdicts
are cached in `.cache.jsonl` keyed by the pair and `PROMPT_VERSION`, so
re-runs cost nothing and a prompt change invalidates cleanly. Both
`candidates.csv` and `.cache.jsonl` are gitignored.

### Adjudication

`claude-sonnet-5`, two passes. The first asks directly. The second
re-examines only the pairs the first called a match, framed
adversarially — make the strongest case that these are distinct places,
*then* rule. The failure this guards against is documented in the sister
corpus: name_bench commit `eab9ceba` corrected labels where the model
had been "over-eager in calling structurally distinct names matches".

A disagreement between the passes never silently flips a label. It
demotes the row to `WEAK` and leaves it for a human.
