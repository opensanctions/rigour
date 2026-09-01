"""Measure the throughput of address keying functions over cases.csv.

Companion to perf.py for the keying (rather than scoring) surface:
runs every distinct address string in the corpus through each
fingerprinter from collapse.py and reports per-call latency, cold
and cache-warm. Requires a release build of the extension
(`make develop`) — debug builds are ~100x slower through the ICU
paths and measure nothing useful.
"""

import time
from typing import cast

import click

from collapse import FINGERPRINTERS, Fingerprinter
from evaluate import load_cases


def _uncached(fingerprinter: Fingerprinter) -> Fingerprinter:
    """Strip the bench-local lru_cache from the Python baselines: the
    downstream keying call sites run them bare, and the Rust path
    keeps its internal analysis LRU either way."""
    return cast(Fingerprinter, getattr(fingerprinter, "__wrapped__", fingerprinter))


def load_addresses() -> list[str]:
    """Distinct address strings, so a cold pass never hits a cache."""
    seen: dict[str, None] = {}
    for case in load_cases():
        seen.setdefault(case.addr1)
        seen.setdefault(case.addr2)
    return list(seen)


def timed_pass(fingerprinter: Fingerprinter, addresses: list[str]) -> float:
    t0 = time.perf_counter()
    for addr in addresses:
        fingerprinter(addr)
    return time.perf_counter() - t0


@click.command()
@click.option("--repeat", default=10, show_default=True, help="Warm passes over the corpus.")
def perf(repeat: int) -> None:
    """Time every fingerprinter over all distinct corpus addresses."""
    addresses = load_addresses()
    click.echo(f"addresses: {len(addresses)}  warm passes: {repeat}")
    for name, cached in FINGERPRINTERS.items():
        fingerprinter = _uncached(cached)
        # First call pays one-time setup (the Rust tagger build).
        t0 = time.perf_counter()
        fingerprinter(addresses[0])
        warmup = time.perf_counter() - t0
        cold = timed_pass(fingerprinter, addresses)
        warm = 0.0
        for _ in range(repeat):
            warm += timed_pass(fingerprinter, addresses)
        calls = repeat * len(addresses)
        click.echo(
            f"{name:>10}: first {warmup * 1e3:8.1f} ms  "
            f"cold {cold / len(addresses) * 1e6:6.1f} us/call  "
            f"warm {warm / calls * 1e6:6.1f} us/call  "
            f"{calls / warm:>10,.0f} calls/s"
        )


if __name__ == "__main__":
    perf()
