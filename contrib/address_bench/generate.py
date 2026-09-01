"""Generate candidate address pairs from an OpenSanctions statements dump.

Stage one of the address_bench pipeline. Emits `candidates.csv`, an
over-sampled and diversity-balanced set of address-string pairs drawn
from five strata. Nothing here decides whether a pair matches — the
stratum is a prior, and `adjudicate.py` assigns the label.
"""

import csv
import random
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import click
import duckdb

from rigour.text.scripts import text_scripts

HERE = Path(__file__).parent
CANDIDATES = HERE / "candidates.csv"

FIELDS = ["stratum", "addr1", "addr2", "dataset1", "dataset2", "scripts", "jaccard"]

#: Max pairs admitted from any one (dataset1, dataset2) combination per
#: stratum. Without it `us_hhs_exclusions + us_sam_exclusions` alone
#: supplies 71.5k of the 169k same-entity cross-dataset pairs.
DATASET_CAP = 40

#: Max share of one stratum any single script bucket may occupy. The
#: raw pools are lopsided: cross-entity postcode blocks are dominated by
#: Cyrillic (ext_ru_egrul), same-entity cross-dataset by Latin (US
#: exclusion lists).
SCRIPT_QUOTA = 0.35

#: Pairs to pull from DuckDB per admitted pair, so the Python-side
#: down-select has slack to satisfy both caps and to discard duplicate
#: pairs without coming up short.
OVERSAMPLE = 20


class Stratum(NamedTuple):
    """One candidate source with its target row count.

    Targets are also the balance control. `block_postcode` is the one
    stratum that yields mostly non-matches, so it carries the weight
    needed to keep the corpus from skewing positive.

    `block_neardupe` is the exception: its target is a *generation*
    count, not a corpus count. It is deliberately over-generated because
    roughly one percent of it are token-identical strings that denote
    different places, and `adjudicate.py` keeps every one of those while
    capping the matches.

    `balance` applies the dataset-pair cap inside SQL. It costs a full
    materialisation and sort of the stratum's pool, which is worth it
    for the same-entity strata — a handful of US exclusion lists
    otherwise crowd out everything else — and ruinous for the
    cross-entity blocks, whose pools run to millions of rows. Those
    rely on the identical cap in `select()` instead.
    """

    name: str
    target: int
    balance: bool
    dataset_cap: int = DATASET_CAP


STRATA = [
    Stratum("same_entity_xds", 1600, True),
    Stratum("same_entity_1ds", 600, True),
    # Raised dataset cap: this is the corpus's main source of
    # non-matches, and at the default cap it runs out of distinct pairs
    # before it runs out of useful ones.
    Stratum("block_postcode", 4000, False, dataset_cap=120),
    Stratum("block_gap", 1000, False),
    Stratum("block_raretoken", 1600, False),
    # Exempt from the dataset cap: the cap exists to keep the *corpus*
    # diverse, and only a few hundred of these ever reach it. Capping
    # generation here just starves the harvest.
    Stratum("block_neardupe", 6000, False, dataset_cap=10**9),
    Stratum("control_same", 100, False),
    Stratum("control_unrelated", 100, False),
]

#: Distinct address strings per entity admitted into the same-entity
#: strata. An entity listing 40 addresses is a data-quality artifact,
#: not 780 useful pairs.
MAX_KEYS_PER_ENTITY = 6

#: Postcode blocks larger than this are generic numbers, not postcodes:
#: they pair `VICKSBURG, MS 39180` with a Russian military unit 39180.
MAX_BLOCK_SIZE = 60

#: Jaccard band for `block_postcode`: related enough to be a plausible
#: candidate, far enough apart to be a genuine discrimination test.
POSTCODE_BAND = (0.3, 0.75)

#: Jaccard band for `block_gap`, the seam between `block_postcode` and
#: `block_neardupe`. Strings this close differ in one component — a unit,
#: a house number, a building name — which is the hardest call there is
#: and where a token-overlap scorer is most likely to be wrong.
GAP_BAND = (0.75, 1.0)

#: Jaccard floor for `block_raretoken`. Below this a shared rare token is
#: usually coincidence rather than a shared locality.
RARE_BAND = (0.4, 1.0)

#: Document-frequency window for a token to be worth blocking on, counted
#: over the postcode-less population. A token in one address blocks
#: nothing; a token in hundreds is a street-type or a city name.
RARE_DF = (2, 40)

#: Minimum length for a blocking token, and minimum token count for both
#: sides of a rare-token pair. Kept lower than `BLOCK_MIN_TOKENS`: these
#: addresses have no postcode and are shorter by nature, and excluding
#: them would defeat the point of the stratum.
RARE_MIN_TOKEN_LEN = 4
RARE_MIN_TOKENS = 4

#: Both sides of a `block_postcode` pair must carry at least this many
#: tokens. The stratum exists to supply *hard negatives* — same locality,
#: different premises — and a city-and-postcode string with no street on
#: it is not that; it is a subset relation, which the same-entity strata
#: already surface in its natural proportion.
BLOCK_MIN_TOKENS = 6

#: Postcode blocks to enumerate pairs within. Enumerating all of them
#: means tens of millions of pairwise Jaccard computations for the sake
#: of a few thousand samples; a random subset of blocks is statistically
#: equivalent and finishes in seconds.
BLOCK_SAMPLE = 12000

BASE_SQL = """
-- The character classes are Unicode-aware on purpose: `[^a-z0-9]` would
-- erase every Cyrillic, Greek, Han and Georgian address down to its
-- digits, collapsing them all onto one empty key.
CREATE OR REPLACE TEMP TABLE v AS
SELECT DISTINCT
    canonical_id,
    value,
    dataset,
    regexp_replace(lower(strip_accents(value)), '[^\\p{{L}}\\p{{N}}]+', '', 'g') AS key,
    regexp_extract(value, '\\b(\\d{{4,6}})\\b', 1) AS pc,
    list_sort(list_distinct(str_split(
        regexp_replace(lower(strip_accents(value)), '[^\\p{{L}}\\p{{N}}]+', ' ', 'g'), ' '
    ))) AS toks,
    array_to_string(list_sort(list_distinct(str_split(
        regexp_replace(lower(strip_accents(value)), '[^\\p{{L}}\\p{{N}}]+', ' ', 'g'), ' '
    ))), ' ') AS tokkey
FROM read_csv('{path}', header=true, all_varchar=true)
WHERE prop IN ('address', 'full')
  AND length(trim(value)) >= 15
  AND len(str_split(regexp_replace(trim(value), '\\s+', ' ', 'g'), ' ')) >= 3;

CREATE OR REPLACE TEMP TABLE nkeys AS
SELECT canonical_id, count(DISTINCT key) AS nk FROM v GROUP BY 1;

CREATE OR REPLACE TEMP TABLE blk AS
SELECT pc FROM (
    SELECT pc FROM v WHERE pc <> '' GROUP BY 1
    HAVING count(*) BETWEEN 2 AND {max_block}
) USING SAMPLE {n_blocks} ROWS;

-- Materialised before the self-join: left to its own devices DuckDB
-- joins the full 522k-row `v` against itself on postcode and only then
-- applies the block filter, which is the difference between seconds and
-- an hour of CPU.
CREATE OR REPLACE TEMP TABLE vb AS
SELECT v.* FROM v JOIN blk ON blk.pc = v.pc;

-- A quarter of usable addresses carry no postcode-like token at all, so
-- the postcode blocks cannot see them. They skew heavily non-Western.
-- Blocking them on a shared rare token reaches that population.
CREATE OR REPLACE TEMP TABLE np AS SELECT * FROM v WHERE pc = '';

CREATE OR REPLACE TEMP TABLE tf AS
SELECT tok, count(*) AS df FROM (SELECT unnest(toks) AS tok FROM np)
WHERE length(tok) >= {rare_len} GROUP BY 1;

CREATE OR REPLACE TEMP TABLE rare AS
SELECT np.canonical_id, np.value, np.dataset, np.key, np.toks, u.tok
FROM np, unnest(np.toks) AS u(tok) JOIN tf ON tf.tok = u.tok
WHERE tf.df BETWEEN {rare_min_df} AND {rare_max_df}
  AND length(u.tok) >= {rare_len}
  AND len(np.toks) >= {rare_min_toks};
"""

#: Same entity, different sources. Richest stratum for transliteration,
#: abbreviation and field-order variation; also the stratum where one
#: source truncates to city + postcode.
SAME_ENTITY_XDS = """
SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
       y.dataset AS dataset2, NULL::DOUBLE AS jaccard
FROM v x JOIN v y ON x.canonical_id = y.canonical_id
JOIN nkeys n ON n.canonical_id = x.canonical_id
WHERE x.key < y.key AND x.dataset <> y.dataset AND n.nk BETWEEN 2 AND {max_keys}
"""

#: Same entity, one source. Contains the CJK original vs English
#: translation pairs (shu_uyghur_companies) alongside genuine
#: multi-site records.
SAME_ENTITY_1DS = """
SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
       y.dataset AS dataset2, NULL::DOUBLE AS jaccard
FROM v x JOIN v y ON x.canonical_id = y.canonical_id
JOIN nkeys n ON n.canonical_id = x.canonical_id
WHERE x.key < y.key AND x.dataset = y.dataset AND n.nk BETWEEN 2 AND {max_keys}
"""

#: Different entities sharing a postcode, in the overlap band where a
#: token-set matcher is most likely to be wrong: same city and postcode,
#: different street or house number.
BLOCK_POSTCODE = """
SELECT addr1, addr2, dataset1, dataset2, jaccard FROM (
    SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
           y.dataset AS dataset2,
           len(list_intersect(x.toks, y.toks))::DOUBLE
               / len(list_distinct(x.toks || y.toks)) AS jaccard
    FROM vb x JOIN vb y ON x.pc = y.pc
    WHERE x.key < y.key AND x.canonical_id <> y.canonical_id
      AND len(x.toks) >= {min_toks} AND len(y.toks) >= {min_toks}
) WHERE jaccard BETWEEN {postcode_lo} AND {postcode_hi}
"""

#: The seam between `block_postcode` and `block_neardupe`: near-identical
#: strings that are not token-identical. Nothing else in the corpus
#: occupies this band, and it is where the incumbent scorer's
#: subset short-circuit does most of its damage.
BLOCK_GAP = """
SELECT addr1, addr2, dataset1, dataset2, jaccard FROM (
    SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
           y.dataset AS dataset2,
           len(list_intersect(x.toks, y.toks))::DOUBLE
               / len(list_distinct(x.toks || y.toks)) AS jaccard
    FROM vb x JOIN vb y ON x.pc = y.pc
    WHERE x.key < y.key AND x.canonical_id <> y.canonical_id
      AND len(x.toks) >= {min_toks} AND len(y.toks) >= {min_toks}
) WHERE jaccard > {gap_lo} AND jaccard < {gap_hi}
"""

#: Postcode-less addresses sharing an uncommon token. The only stratum
#: that reaches the quarter of the data with no postcode to block on.
BLOCK_RARETOKEN = """
SELECT addr1, addr2, dataset1, dataset2, jaccard FROM (
    SELECT DISTINCT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
           y.dataset AS dataset2,
           len(list_intersect(x.toks, y.toks))::DOUBLE
               / len(list_distinct(x.toks || y.toks)) AS jaccard
    FROM rare x JOIN rare y ON x.tok = y.tok
    WHERE x.key < y.key AND x.canonical_id <> y.canonical_id
) WHERE jaccard >= {rare_lo} AND jaccard < {rare_hi}
"""

#: Different entities, same token set, different rendering. Shared
#: premises and registered-agent addresses — the stratum that catches a
#: matcher being too strict rather than too loose. Matching on the token
#: key is an equi-join, so this costs a hash join rather than the
#: pairwise Jaccard sweep the postcode blocks need.
BLOCK_NEARDUPE = """
SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
       y.dataset AS dataset2, 1.0::DOUBLE AS jaccard
FROM v x JOIN v y ON x.tokkey = y.tokkey
WHERE x.key < y.key AND x.canonical_id <> y.canonical_id
"""

#: Floor and ceiling controls. Identical modulo case and punctuation,
#: and pairs with no shared tokens at all.
CONTROL_SAME = """
SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
       y.dataset AS dataset2, 1.0::DOUBLE AS jaccard
FROM v x JOIN v y ON x.key = y.key
WHERE x.value < y.value
"""

CONTROL_UNRELATED = """
SELECT addr1, addr2, dataset1, dataset2, jaccard FROM (
    SELECT x.value AS addr1, y.value AS addr2, x.dataset AS dataset1,
           y.dataset AS dataset2,
           len(list_intersect(x.toks, y.toks))::DOUBLE
               / len(list_distinct(x.toks || y.toks)) AS jaccard
    FROM (SELECT * FROM v USING SAMPLE 800 ROWS) x
    CROSS JOIN (SELECT * FROM v USING SAMPLE 800 ROWS) y
    WHERE x.key < y.key AND x.canonical_id <> y.canonical_id
) WHERE jaccard = 0.0
"""

QUERIES = {
    "same_entity_xds": SAME_ENTITY_XDS,
    "same_entity_1ds": SAME_ENTITY_1DS,
    "block_postcode": BLOCK_POSTCODE,
    "block_gap": BLOCK_GAP,
    "block_raretoken": BLOCK_RARETOKEN,
    "block_neardupe": BLOCK_NEARDUPE,
    "control_same": CONTROL_SAME,
    "control_unrelated": CONTROL_UNRELATED,
}


def script_bucket(addr1: str, addr2: str) -> str:
    """Name the writing systems a pair spans, for quota accounting."""
    scripts = text_scripts(addr1) | text_scripts(addr2)
    if not len(scripts):
        return "None"
    return "+".join(sorted(scripts))


def fetch(con: duckdb.DuckDBPyConnection, stratum: Stratum) -> list[dict[str, Any]]:
    """Pull an over-sampled, dataset-balanced slice of one stratum.

    Over-samples by `OVERSAMPLE` so `select()` has slack to satisfy both
    caps without coming up short of the target.
    """
    inner = QUERIES[stratum.name].format(
        max_keys=MAX_KEYS_PER_ENTITY,
        max_block=MAX_BLOCK_SIZE,
        min_toks=BLOCK_MIN_TOKENS,
        postcode_lo=POSTCODE_BAND[0],
        postcode_hi=POSTCODE_BAND[1],
        gap_lo=GAP_BAND[0],
        gap_hi=GAP_BAND[1],
        rare_lo=RARE_BAND[0],
        rare_hi=RARE_BAND[1],
    )
    limit = stratum.target * OVERSAMPLE
    if stratum.balance:
        inner = f"""
        SELECT addr1, addr2, dataset1, dataset2, jaccard FROM (
            SELECT *, row_number() OVER (
                PARTITION BY least(dataset1, dataset2), greatest(dataset1, dataset2)
                ORDER BY random()
            ) AS rn
            FROM ({inner})
        ) WHERE rn <= {stratum.dataset_cap * 3}
        """
    # The subquery is load-bearing: DuckDB pushes `USING SAMPLE` below a
    # trailing WHERE, so sampling an unwrapped filtered query draws from
    # the pre-filter pool and returns far fewer rows than asked for.
    rows = con.execute(f"SELECT * FROM ({inner}) USING SAMPLE {limit} ROWS").fetchall()
    return [
        dict(zip(("addr1", "addr2", "dataset1", "dataset2", "jaccard"), r))
        for r in rows
    ]


def select(rows: list[dict[str, Any]], stratum: Stratum) -> Iterator[dict[str, Any]]:
    """Admit rows under the dataset-pair cap and per-script quota.

    Runs twice: a strict pass honouring both caps, then a relaxed pass
    that keeps only the dataset cap. Without the second pass a stratum
    whose pool is genuinely single-script (the CJK translation pairs)
    would come up short of its target.
    """
    random.shuffle(rows)
    script_cap = max(1, int(stratum.target * SCRIPT_QUOTA))
    by_dataset: Counter[tuple[str, str]] = Counter()
    by_script: Counter[str] = Counter()
    taken: set[int] = set()
    # One address pair can reach a stratum by more than one route — two
    # dataset combinations for the same strings, or two shared rare
    # tokens — and would otherwise spend the target twice.
    seen: set[tuple[str, str]] = set()
    admitted = 0

    for enforce_script in (True, False):
        for index, row in enumerate(rows):
            if admitted >= stratum.target:
                return
            if index in taken:
                continue
            pair = (row["addr1"], row["addr2"])
            if pair in seen:
                continue
            ds = (
                min(row["dataset1"], row["dataset2"]),
                max(row["dataset1"], row["dataset2"]),
            )
            if by_dataset[ds] >= stratum.dataset_cap:
                continue
            bucket = script_bucket(row["addr1"], row["addr2"])
            if enforce_script and by_script[bucket] >= script_cap:
                continue
            by_dataset[ds] += 1
            by_script[bucket] += 1
            seen.add(pair)
            taken.add(index)
            admitted += 1
            row["stratum"] = stratum.name
            row["scripts"] = bucket
            yield row


@click.command()
@click.option(
    "--statements",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="OpenSanctions statements CSV dump.",
)
@click.option("--memory", default="12GB", help="DuckDB memory limit.")
@click.option("--seed", default=42, help="Shuffle seed for the down-select.")
def main(statements: Path, memory: str, seed: int) -> None:
    """Write candidates.csv from a statements dump."""
    random.seed(seed)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory}'")
    click.echo(f"Reading {statements} ...", err=True)
    con.execute(
        BASE_SQL.format(
            path=statements,
            max_block=MAX_BLOCK_SIZE,
            n_blocks=BLOCK_SAMPLE,
            rare_len=RARE_MIN_TOKEN_LEN,
            rare_min_df=RARE_DF[0],
            rare_max_df=RARE_DF[1],
            rare_min_toks=RARE_MIN_TOKENS,
        )
    )
    total = con.execute("SELECT count(*) FROM v").fetchone()
    click.echo(f"  {total[0] if total else 0} usable address strings", err=True)

    with open(CANDIDATES, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for stratum in STRATA:
            pool = fetch(con, stratum)
            rows = list(select(pool, stratum))
            for row in rows:
                writer.writerow(row)
            click.echo(
                f"  {stratum.name}: {len(rows)} of {stratum.target} "
                f"(pool {len(pool)})",
                err=True,
            )
    click.echo(f"Wrote {CANDIDATES}", err=True)


if __name__ == "__main__":
    main()
