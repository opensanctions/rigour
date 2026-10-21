"""Measure how often `maybe_ascii` lands on a human Latin spelling.

For each name group in a person_names file, transliterate every non-Latin
form that `maybe_ascii` admits and compare it against the group's pure-ASCII
forms. Absolute rates stay low because groups mix romanization schemes
(German, French, ...); compare the numbers between builds instead.

Usage: python contrib/translit_divergence.py [PATH] [--misses CSV]
"""

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from rigour.text.distance import levenshtein
from rigour.text.scripts import text_scripts
from rigour.text.translit import maybe_ascii, should_ascii

DEFAULT_PATH = Path(__file__).parent.parent / "rust/data/names/person_names.txt"


@dataclass
class Stats:
    n: int = 0
    hits: int = 0
    near: int = 0
    dist_sum: int = 0


def parse_line(line: str) -> list[str]:
    forms, _, _ = line.partition(" => ")
    return [f.strip() for f in forms.split(",") if f.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure maybe_ascii divergence from Latin spellings."
    )
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--misses", type=Path, help="write non-hits to this CSV")
    args = parser.parse_args()

    stats: dict[str, Stats] = defaultdict(Stats)
    misses: list[tuple[str, str, str, int]] = []
    with open(args.path, "r", encoding="utf-8") as fh:
        for line in fh:
            forms = parse_line(line)
            refs = [f for f in forms if f.isascii()]
            if not refs:
                continue
            for form in forms:
                scripts = text_scripts(form)
                if "Latin" in scripts or not should_ascii(form):
                    continue
                cand = maybe_ascii(form).lower()
                dist, nearest = min((levenshtein(cand, r), r) for r in refs)
                for key in (",".join(sorted(scripts)), "TOTAL"):
                    st = stats[key]
                    st.n += 1
                    st.hits += dist == 0
                    st.near += dist <= 1
                    st.dist_sum += dist
                if dist > 0:
                    misses.append((form, cand, nearest, dist))

    print(f"{'script':<18} {'n':>8} {'hit %':>7} {'≤1 %':>7} {'mean dist':>9}")
    for key in sorted(stats, key=lambda k: (k == "TOTAL", -stats[k].n)):
        st = stats[key]
        print(
            f"{key:<18} {st.n:>8} {100 * st.hits / st.n:>7.2f} "
            f"{100 * st.near / st.n:>7.2f} {st.dist_sum / st.n:>9.3f}"
        )

    if args.misses is not None:
        with open(args.misses, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["source", "candidate", "nearest_ref", "dist"])
            writer.writerows(misses)


if __name__ == "__main__":
    main()
