"""Output-compatibility check: `maybe_ascii` vs `normality.ascii_text`.

For every name in `contrib/sample_names.csv` that `should_ascii`
admits (Latin / Cyrillic / Greek / Armenian / Georgian / Hangul),
run both functions and compare the outputs. Group divergences by
the input's dominant script so the patterns are legible.

Three kinds of diff:

- **exact**: byte-identical output.
- **case-only**: outputs equal after `casefold()`. Trivial — one
  backend uppercases (or titlecases) where the other doesn't.
- **semantic**: outputs differ even after casefold. These are the
  interesting ones — character-substitution differences, apostrophe
  conventions, w-vs-v, and so on. Real quality / compatibility
  signal.

Rejected inputs (Han, Arabic, Thai, etc.) are skipped: `maybe_ascii`
identity-passes them by design, so every rejected input would
trivially "diverge" from normality's transliteration.
"""

import csv
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, List, Tuple

from normality import ascii_text as normality_ascii

from rigour.text.translit import maybe_ascii, should_ascii

CORPUS = Path(__file__).parent.parent / "contrib" / "sample_names.csv"
SAMPLES_PER_SCRIPT = 8


def load_names() -> List[str]:
    with open(CORPUS, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        return [row[0] for row in reader]


def primary_script(text: str) -> str:
    """First meaningful script encountered in text. Latin-with-diacritics
    and Latin-ASCII both return 'Latin'; non-Latin returns the script's
    Unicode-name prefix (CYRILLIC, GREEK, etc.)."""
    for ch in text:
        if not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        tok = name.split()[0]
        if tok in (
            "LATIN",
            "CYRILLIC",
            "GREEK",
            "ARMENIAN",
            "GEORGIAN",
            "HANGUL",
        ):
            return tok.title()
    return "None"


def classify(a: str, b: str) -> str:
    if a == b:
        return "exact"
    if a.casefold() == b.casefold():
        return "case-only"
    return "semantic"


def main() -> None:
    names = load_names()
    admitted = [n for n in names if should_ascii(n)]
    print(
        f"Corpus: {len(names)} total, {len(admitted)} admitted "
        f"({len(names) - len(admitted)} rejected, skipped)"
    )
    print()

    counts: DefaultDict[str, DefaultDict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    diffs: DefaultDict[str, List[Tuple[str, str, str, str]]] = defaultdict(list)

    for name in admitted:
        a = maybe_ascii(name)
        b = normality_ascii(name)
        kind = classify(a, b)
        script = primary_script(name)
        counts[script][kind] += 1
        if kind != "exact":
            diffs[script].append((kind, name, a, b))

    totals: DefaultDict[str, int] = defaultdict(int)
    for script_counts in counts.values():
        for kind, n in script_counts.items():
            totals[kind] += n
    grand = sum(totals.values())

    print("== Summary ==")
    print(f"{'':<12} {'exact':>10} {'case-only':>11} {'semantic':>10} {'total':>8}")
    for script in sorted(counts):
        c = counts[script]
        row_total = c["exact"] + c["case-only"] + c["semantic"]
        print(
            f"{script:<12} {c['exact']:>10} {c['case-only']:>11} "
            f"{c['semantic']:>10} {row_total:>8}"
        )
    print(
        f"{'TOTAL':<12} {totals['exact']:>10} {totals['case-only']:>11} "
        f"{totals['semantic']:>10} {grand:>8}"
    )
    agree_pct = 100.0 * totals["exact"] / grand if grand else 0.0
    print(f"\nExact agreement: {agree_pct:.1f}%")
    print()

    if not any(diffs.values()):
        print("No divergences — byte-identical across the admitted bucket.")
        return

    for script in sorted(diffs):
        script_diffs = diffs[script]
        if not script_diffs:
            continue
        print(f"== {script} — {len(script_diffs)} diffs (showing up to {SAMPLES_PER_SCRIPT}) ==")
        # Show semantic diffs first — they're the interesting ones.
        script_diffs.sort(key=lambda t: (0 if t[0] == "semantic" else 1, t[1]))
        for kind, name, a, b in script_diffs[:SAMPLES_PER_SCRIPT]:
            print(f"  [{kind}] input: {name!r}")
            print(f"          rigour    : {a!r}")
            print(f"          normality : {b!r}")
        print()


if __name__ == "__main__":
    main()
