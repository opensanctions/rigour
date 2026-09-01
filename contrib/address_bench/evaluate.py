"""Evaluate an address scorer against the labelled corpus in cases.csv.

Stage three of the address_bench pipeline. Runs one scoring mechanism
over every labelled pair and reports ranking quality (AUC), accuracy at
the best fixed threshold, per-quality and per-category slices, and the
worst individual failures. The scorers are local reimplementations of
the downstream comparison logic, so the bench measures the mechanism
without importing nomenklatura or followthemoney.
"""

import csv
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from rigour.addresses import normalize_address, remove_address_keywords
from rigour.text import levenshtein_similarity

HERE = Path(__file__).parent
CASES = HERE / "cases.csv"

#: Categories with fewer rows than this are folded into "(other)" in
#: the per-category table.
MIN_CATEGORY = 25

#: Worst false positives / false negatives to list.
FAILURES = 10

Scorer = Callable[[str, str], float]


@dataclass(frozen=True)
class Case:
    addr1: str
    addr2: str
    is_match: bool
    quality: str
    category: str


@dataclass(frozen=True)
class Result:
    case: Case
    score: float


@lru_cache(maxsize=30000)
def _nk_tokens(addr: str) -> frozenset[str]:
    norm = normalize_address(addr, latinize=True)
    if norm is None:
        return frozenset()
    removed = remove_address_keywords(norm, latinize=True)
    if removed is None:
        return frozenset()
    return frozenset(t for t in removed.split() if len(t) > 0)


def score_nomenklatura(addr1: str, addr2: str) -> float:
    """Reimplementation of nomenklatura._address_match for one string pair."""
    tokens1, tokens2 = _nk_tokens(addr1), _nk_tokens(addr2)
    if len(tokens1) == 0 or len(tokens2) == 0:
        return 0.0
    overlap = tokens1.intersection(tokens2)
    if len(overlap) == len(tokens1) or len(overlap) == len(tokens2):
        return 1.0
    rem1 = sorted(tokens1 - overlap)
    rem2 = sorted(tokens2 - overlap)
    fuzzy1, fuzzy2 = " ".join(rem1), " ".join(rem2)
    fuzzy_len = max(len(fuzzy1), len(fuzzy2))
    sim = levenshtein_similarity(fuzzy1, fuzzy2, max_edits=fuzzy_len)
    rem_len = max(len(rem1), len(rem2))
    return (len(overlap) + (rem_len * sim)) / (rem_len + len(overlap))


@lru_cache(maxsize=30000)
def _ftm_norm(addr: str) -> str | None:
    return normalize_address(addr)


def score_ftm(addr1: str, addr2: str) -> float:
    """Reimplementation of followthemoney AddressType.compare."""
    norm1, norm2 = _ftm_norm(addr1), _ftm_norm(addr2)
    if norm1 is None or norm2 is None:
        return 0.0
    base_len = min(len(norm1), len(norm2))
    max_edits = int(base_len * 0.33)
    return levenshtein_similarity(norm1, norm2, max_edits=max_edits)


SCORERS: dict[str, Scorer] = {
    "nomenklatura": score_nomenklatura,
    "ftm": score_ftm,
}


def load_cases() -> list[Case]:
    cases: list[Case] = []
    with open(CASES, "r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cases.append(
                Case(
                    addr1=row["addr1"],
                    addr2=row["addr2"],
                    is_match=row["is_match"] == "true",
                    quality=row["quality"],
                    category=row["category"],
                )
            )
    return cases


def roc_auc(results: list[Result]) -> float:
    """Mann-Whitney AUC with average ranks for tied scores."""
    pos = sum(1 for r in results if r.case.is_match)
    neg = len(results) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    ranked = sorted(results, key=lambda r: r.score)
    rank_sum_pos = 0.0
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j].score == ranked[i].score:
            j += 1
        avg_rank = (i + 1 + j) / 2
        for k in range(i, j):
            if ranked[k].case.is_match:
                rank_sum_pos += avg_rank
        i = j
    u = rank_sum_pos - pos * (pos + 1) / 2
    return u / (pos * neg)


def best_threshold(results: list[Result]) -> tuple[float, float]:
    """Threshold (predict match at score >= t) maximizing accuracy."""
    total = len(results)
    total_pos = sum(1 for r in results if r.case.is_match)
    ranked = sorted(results, key=lambda r: r.score, reverse=True)
    best_t, best_acc = 1.01, (total - total_pos) / total
    tp, fp = 0, 0
    i = 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j].score == ranked[i].score:
            if ranked[j].case.is_match:
                tp += 1
            else:
                fp += 1
            j += 1
        acc = (tp + (total - total_pos - fp)) / total
        if acc > best_acc:
            best_t, best_acc = ranked[i].score, acc
        i = j
    return best_t, best_acc


def _mean(scores: list[float]) -> float:
    if len(scores) == 0:
        return float("nan")
    return sum(scores) / len(scores)


def slice_table(
    console: Console, title: str, groups: dict[str, list[Result]], threshold: float
) -> None:
    table = Table(title=title)
    table.add_column("slice")
    table.add_column("n", justify="right")
    table.add_column("match", justify="right")
    table.add_column("avg s|match", justify="right")
    table.add_column("avg s|non", justify="right")
    table.add_column("errors", justify="right")
    table.add_column("err rate", justify="right")
    for name in sorted(groups, key=lambda g: len(groups[g]), reverse=True):
        results = groups[name]
        match_scores = [r.score for r in results if r.case.is_match]
        non_scores = [r.score for r in results if not r.case.is_match]
        errors = sum(1 for r in results if (r.score >= threshold) != r.case.is_match)
        table.add_row(
            name,
            str(len(results)),
            f"{len(match_scores) / len(results):.0%}",
            f"{_mean(match_scores):.3f}",
            f"{_mean(non_scores):.3f}",
            str(errors),
            f"{errors / len(results):.1%}",
        )
    console.print(table)


def failures_table(console: Console, title: str, results: list[Result]) -> None:
    table = Table(title=title)
    table.add_column("score", justify="right")
    table.add_column("category")
    table.add_column("addr1", max_width=48)
    table.add_column("addr2", max_width=48)
    for r in results:
        table.add_row(f"{r.score:.3f}", r.case.category, r.case.addr1, r.case.addr2)
    console.print(table)


@click.command()
@click.option(
    "--scorer",
    "scorer_name",
    type=click.Choice(sorted(SCORERS)),
    default="nomenklatura",
    show_default=True,
    help="Scoring mechanism to evaluate.",
)
def evaluate(scorer_name: str) -> None:
    """Score every pair in cases.csv and report quality metrics."""
    scorer = SCORERS[scorer_name]
    cases = load_cases()
    results = [Result(case=c, score=scorer(c.addr1, c.addr2)) for c in cases]

    console = Console()
    auc = roc_auc(results)
    threshold, accuracy = best_threshold(results)
    console.print(f"\n[bold]{scorer_name}[/bold] on {len(results)} pairs")
    console.print(f"AUC: [bold]{auc:.4f}[/bold]")
    console.print(
        f"best threshold: {threshold:.3f}  accuracy: [bold]{accuracy:.2%}[/bold]"
    )
    strong = [r for r in results if r.case.quality == "STRONG"]
    console.print(f"AUC (STRONG only): {roc_auc(strong):.4f}\n")

    by_quality: dict[str, list[Result]] = {}
    for r in results:
        by_quality.setdefault(r.case.quality, []).append(r)
    slice_table(console, "by quality", by_quality, threshold)

    counts: dict[str, int] = {}
    for r in results:
        counts[r.case.category] = counts.get(r.case.category, 0) + 1
    by_category: dict[str, list[Result]] = {}
    for r in results:
        key = r.case.category if counts[r.case.category] >= MIN_CATEGORY else "(other)"
        by_category.setdefault(key, []).append(r)
    slice_table(console, "by category", by_category, threshold)

    false_pos = sorted(
        (r for r in results if not r.case.is_match and r.score >= threshold),
        key=lambda r: r.score,
        reverse=True,
    )
    failures_table(console, "worst false positives", false_pos[:FAILURES])
    false_neg = sorted(
        (r for r in results if r.case.is_match and r.score < threshold),
        key=lambda r: r.score,
    )
    failures_table(console, "worst false negatives", false_neg[:FAILURES])


if __name__ == "__main__":
    evaluate()
