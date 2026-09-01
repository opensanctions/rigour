"""Measure the throughput of the Rust address scorer over cases.csv.

Runs every pair in the corpus `--repeat` times through
`rigour._core.compare_address` and reports per-call latency and
throughput, plus a percentile breakdown from individually timed
calls. Requires a release build of the extension (`make develop`) —
debug builds are ~100x slower through the ICU paths and measure
nothing useful.
"""

import csv
import time
from pathlib import Path
from statistics import mean

import click

from rigour._core import compare_address

HERE = Path(__file__).parent
CASES = HERE / "cases.csv"


def load_pairs() -> list[tuple[str, str]]:
    with open(CASES, encoding="utf-8") as fh:
        return [(row["addr1"], row["addr2"]) for row in csv.DictReader(fh)]


@click.command()
@click.option("--repeat", default=10, show_default=True, help="Full passes over the corpus.")
def perf(repeat: int) -> None:
    """Time compare_address over all corpus pairs."""
    pairs = load_pairs()

    # Warm-up: first call builds the lazy tagger automaton.
    t0 = time.perf_counter()
    compare_address(pairs[0][0], pairs[0][1])
    warmup = time.perf_counter() - t0

    # Bulk throughput: chunk-timed to keep timer overhead out.
    t0 = time.perf_counter()
    for _ in range(repeat):
        for a, b in pairs:
            compare_address(a, b)
    elapsed = time.perf_counter() - t0
    calls = repeat * len(pairs)

    # Per-pair latency profile from one individually-timed pass.
    laps: list[float] = []
    for a, b in pairs:
        t0 = time.perf_counter()
        compare_address(a, b)
        laps.append(time.perf_counter() - t0)
    laps.sort()

    def pct(p: float) -> float:
        return laps[min(int(len(laps) * p), len(laps) - 1)] * 1e6

    click.echo(f"pairs: {len(pairs)}  repeats: {repeat}  calls: {calls}")
    click.echo(f"first call (tagger build): {warmup * 1e3:.1f} ms")
    click.echo(f"bulk: {elapsed:.2f} s  {elapsed / calls * 1e6:.1f} us/call  {calls / elapsed:,.0f} calls/s")
    click.echo(
        f"per-call: mean {mean(laps) * 1e6:.1f} us  "
        f"p50 {pct(0.50):.1f}  p90 {pct(0.90):.1f}  p99 {pct(0.99):.1f}  "
        f"max {laps[-1] * 1e6:.1f} us"
    )

    # The nomenklatura call shape: one query against many candidates.
    # Without a cache the query side is re-analyzed every call; this
    # number is what decides whether analysis memoization is needed.
    query = pairs[0][0]
    results = [b for _, b in pairs[:1000]]
    t0 = time.perf_counter()
    for b in results:
        compare_address(query, b)
    one_n = time.perf_counter() - t0
    click.echo(f"1xN shape: 1 query x {len(results)} results in {one_n * 1e3:.1f} ms")


if __name__ == "__main__":
    perf()
