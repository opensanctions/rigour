"""Rank address tokens that no rigour resource currently recognises.

Reads an OpenSanctions statements dump, takes every `Address:full` /
`Thing:address` value, and runs it through the same normalisation path
the matcher uses — `normalize_address` then `remove_address_keywords`.
Whatever survives that is, by construction, a token covered by neither
`resources/addresses/forms.yml`, the ordinals table, nor the territories
database. Ranked by how many distinct addresses carry it, the survivors
are the candidate set for extending `forms.yml`.

Coverage is checked with `latinize=False`, so tokens appear in their
source script — the form in which they would be added to `forms.yml`.

Usage:
    python address_tokens.py ~/Data/statements-apr26.csv -o tokens.csv
"""

import csv
import sys
from collections.abc import Iterator
from pathlib import Path

import click
import duckdb

from rigour.addresses import normalize_address, remove_address_keywords
from rigour.text.scripts import text_scripts

FIELDS = ["token", "addresses", "datasets", "scripts", "example"]

#: Distinct address values, each with the datasets it occurs in. Counting
#: per distinct value rather than per statement keeps one boilerplate
#: address that is stated ten thousand times from dominating the ranking.
VALUES_SQL = """
SELECT value, list(DISTINCT dataset) AS datasets
FROM read_csv('{path}', header=true, all_varchar=true)
WHERE prop IN ('address', 'full') AND length(trim(value)) > 0
GROUP BY 1
"""


def scripts_of(token: str) -> str:
    """Name the Unicode scripts a token is written in, for curation."""
    return "+".join(sorted(text_scripts(token))) or "none"


def residue(value: str) -> list[str]:
    """Return the tokens of one address that rigour does not recognise."""
    norm = normalize_address(value)
    if norm is None:
        return []
    stripped = remove_address_keywords(norm)
    if stripped is None:
        return []
    return stripped.split()


def read_values(path: Path) -> Iterator[tuple[str, list[str]]]:
    """Stream distinct address values and their datasets out of the dump."""
    con = duckdb.connect()
    con.execute(f"CREATE TEMP TABLE av AS {VALUES_SQL.format(path=path)}")
    result = con.execute("SELECT value, datasets FROM av")
    while True:
        batch = result.fetchmany(10_000)
        if len(batch) == 0:
            return
        for value, datasets in batch:
            yield value, datasets


@click.command()
@click.argument("statements", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--outfile", type=click.Path(path_type=Path), default=None,
              help="Write the full ranking to this CSV instead of stdout.")
@click.option("--min-length", type=int, default=2, show_default=True,
              help="Discard tokens shorter than this.")
@click.option("--min-count", type=int, default=20, show_default=True,
              help="Discard tokens carried by fewer distinct addresses.")
@click.option("--limit", type=int, default=500, show_default=True,
              help="Rows to print when writing to stdout.")
def main(
    statements: Path, outfile: Path | None, min_length: int, min_count: int, limit: int
) -> None:
    """Rank uncovered address tokens in an OpenSanctions statements dump."""
    counts: dict[str, int] = {}
    sources: dict[str, set[int]] = {}
    examples: dict[str, str] = {}
    dataset_ids: dict[str, int] = {}

    for n, (value, datasets) in enumerate(read_values(statements)):
        if n % 50_000 == 0:
            click.echo(f"  ... {n:,} addresses, {len(counts):,} tokens", err=True)
        ids = {dataset_ids.setdefault(d, len(dataset_ids)) for d in datasets}
        for token in set(residue(value)):
            if len(token) < min_length:
                continue
            # House numbers, postcodes and building numbers are not
            # keyword candidates, and any digit is enough to mark one.
            if any(c.isdigit() for c in token):
                continue
            counts[token] = counts.get(token, 0) + 1
            sources.setdefault(token, set()).update(ids)
            examples.setdefault(token, value)

    ranked = sorted(
        ((t, c) for t, c in counts.items() if c >= min_count),
        key=lambda tc: (-tc[1], tc[0]),
    )
    click.echo(f"{len(ranked):,} tokens at >= {min_count} addresses", err=True)

    rows = [
        {
            "token": token,
            "addresses": count,
            "datasets": len(sources[token]),
            "scripts": scripts_of(token),
            "example": examples[token],
        }
        for token, count in ranked
    ]
    if outfile is None:
        writer = csv.DictWriter(sys.stdout, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows[:limit])
        return
    with open(outfile, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    click.echo(f"Wrote {len(rows):,} rows to {outfile}", err=True)


if __name__ == "__main__":
    main()
