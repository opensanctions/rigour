"""Measure address fingerprint collapse rates on the labelled corpus.

Companion to evaluate.py for the keying (rather than scoring) surface:
a fingerprinter maps one address string to a single stable key or
None, and a pair "collapses" when both keys exist and are equal.
Collapses on matching pairs measure the recall of exact keying;
collapses on non-matching pairs are false merges — the metric that
decides whether a hard-normalizing fingerprint is safe to use as a
graph node key. The baseline fingerprinters are local
reimplementations of the downstream keying logic, so the bench
measures the mechanism without importing followthemoney or zavod.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import click
from normality import slugify_text
from rich.console import Console
from rich.table import Table

from evaluate import MIN_CATEGORY, Case, load_cases
from rigour.addresses import normalize_address

#: Worst false collapses to list.
SAMPLES = 15

Fingerprinter = Callable[[str], str | None]


@lru_cache(maxsize=30000)
def fp_slugify(addr: str) -> str | None:
    """The zavod address-ID keying: slugify the raw string."""
    return slugify_text(addr)


@lru_cache(maxsize=30000)
def fp_ftm(addr: str) -> str | None:
    """The followthemoney node_id keying: normalize, then slugify."""
    norm = normalize_address(addr)
    if norm is None:
        return None
    return slugify_text(norm)


FINGERPRINTERS: dict[str, Fingerprinter] = {
    "slugify": fp_slugify,
    "ftm": fp_ftm,
}


@dataclass(frozen=True)
class Keyed:
    case: Case
    fp1: str | None
    fp2: str | None

    @property
    def collapsed(self) -> bool:
        return self.fp1 is not None and self.fp1 == self.fp2


def _rate(hits: int, total: int) -> str:
    if total == 0:
        return "-"
    return f"{hits / total:.1%}"


def slice_table(console: Console, title: str, groups: dict[str, list[Keyed]]) -> None:
    table = Table(title=title)
    table.add_column("slice")
    table.add_column("n", justify="right")
    table.add_column("match", justify="right")
    table.add_column("true collapse", justify="right")
    table.add_column("false collapse", justify="right")
    table.add_column("none", justify="right")
    for name in sorted(groups, key=lambda g: len(groups[g]), reverse=True):
        keyed = groups[name]
        matches = [k for k in keyed if k.case.is_match]
        non = [k for k in keyed if not k.case.is_match]
        nones = sum((k.fp1 is None) + (k.fp2 is None) for k in keyed)
        table.add_row(
            name,
            str(len(keyed)),
            f"{len(matches) / len(keyed):.0%}",
            _rate(sum(1 for k in matches if k.collapsed), len(matches)),
            _rate(sum(1 for k in non if k.collapsed), len(non)),
            _rate(nones, len(keyed) * 2),
        )
    console.print(table)


def false_collapse_table(console: Console, keyed: list[Keyed]) -> None:
    table = Table(title=f"false collapses (first {SAMPLES})")
    table.add_column("category")
    table.add_column("addr1", max_width=44)
    table.add_column("addr2", max_width=44)
    table.add_column("fingerprint", max_width=40)
    for k in keyed[:SAMPLES]:
        table.add_row(k.case.category, k.case.addr1, k.case.addr2, k.fp1 or "")
    console.print(table)


@click.command()
@click.option(
    "--fingerprint",
    "fp_name",
    type=click.Choice(sorted(FINGERPRINTERS)),
    default="ftm",
    show_default=True,
    help="Fingerprinting mechanism to evaluate.",
)
def collapse(fp_name: str) -> None:
    """Fingerprint both sides of every pair and report collapse rates."""
    fingerprinter = FINGERPRINTERS[fp_name]
    keyed = [
        Keyed(case=c, fp1=fingerprinter(c.addr1), fp2=fingerprinter(c.addr2))
        for c in load_cases()
    ]

    console = Console()
    matches = [k for k in keyed if k.case.is_match]
    non = [k for k in keyed if not k.case.is_match]
    true_hits = sum(1 for k in matches if k.collapsed)
    false_hits = sum(1 for k in non if k.collapsed)
    nones = sum((k.fp1 is None) + (k.fp2 is None) for k in keyed)
    console.print(f"\n[bold]{fp_name}[/bold] on {len(keyed)} pairs")
    console.print(
        f"true collapses: [bold]{true_hits}/{len(matches)}"
        f" ({true_hits / len(matches):.1%})[/bold]"
    )
    console.print(
        f"false collapses: [bold]{false_hits}/{len(non)}"
        f" ({false_hits / len(non):.2%})[/bold]"
    )
    console.print(f"fingerprint is None: {nones}/{len(keyed) * 2} addresses\n")

    by_quality: dict[str, list[Keyed]] = {}
    for k in keyed:
        by_quality.setdefault(k.case.quality, []).append(k)
    slice_table(console, "by quality", by_quality)

    counts: dict[str, int] = {}
    for k in keyed:
        counts[k.case.category] = counts.get(k.case.category, 0) + 1
    by_category: dict[str, list[Keyed]] = {}
    for k in keyed:
        key = k.case.category if counts[k.case.category] >= MIN_CATEGORY else "(other)"
        by_category.setdefault(key, []).append(k)
    slice_table(console, "by category", by_category)

    false_collapse_table(console, [k for k in non if k.collapsed])


if __name__ == "__main__":
    collapse()
