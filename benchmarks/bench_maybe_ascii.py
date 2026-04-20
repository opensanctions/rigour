"""Relative-speed benchmark: rigour `maybe_ascii` vs `normality.ascii_text`.

Two timing scenarios per function, per bucket:

- **Cold** — each pass suffixes every name with a unique marker so no
  call is a cache hit. Measures real per-call cost: FFI + script
  detection + ICU4X transliteration + LRU insert. Representative of
  one-shot pipelines (OpenSanctions export over millions of distinct
  entity names).
- **Hot** — every pass uses the same inputs; the LRU caches fill on
  pass 1 and subsequent passes hit. Measures cache-lookup infrastructure
  cost.

Corpus is split by `should_ascii`:

- **Admitted** — Latin/Cyrillic/Greek/Armenian/Georgian/Hangul. Both
  functions do real transliteration work (when cold).
- **Rejected** — CJK/Arabic/Hebrew/Thai/etc. `maybe_ascii` identity-
  passes; `normality.ascii_text` still runs its full PyICU pipeline.
  The narrowing's perf benefit shows up here.
"""

import csv
import statistics
import time
from pathlib import Path
from typing import Callable, List

from normality import ascii_text as normality_ascii

from rigour.text.translit import maybe_ascii, should_ascii

CORPUS = Path(__file__).parent.parent / "contrib" / "sample_names.csv"
PASSES = 5


def load_names() -> List[str]:
    with open(CORPUS, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        return [row[0] for row in reader]


def run_pass(fn: Callable[[str], str], inputs: List[str]) -> float:
    start = time.perf_counter()
    for s in inputs:
        fn(s)
    return time.perf_counter() - start


def bench_cold(label: str, fn: Callable[[str], str], names: List[str]) -> None:
    """Each pass suffixes every name uniquely → every call is a cache miss."""
    n = len(names)
    # Warmup — prime ICU4X transliterator init, Python import-time
    # machinery, allocator. Uses un-suffixed names; measured passes
    # below use unique suffixes so the warmup doesn't pollute.
    for s in names:
        fn(s)
    times: List[float] = []
    for p in range(PASSES):
        suffix = f" {p}X{p}"
        mutated = [s + suffix for s in names]
        times.append(run_pass(fn, mutated))
    med = statistics.median(times)
    print(f"  {label}")
    for i, t in enumerate(times):
        print(f"    pass {i + 1}: {t * 1000:7.2f} ms   ({n / t:>10,.0f} names/sec)")
    print(f"    median:  {med * 1000:7.2f} ms   ({n / med:>10,.0f} names/sec)")


def bench_hot(label: str, fn: Callable[[str], str], names: List[str]) -> None:
    """All passes use the same inputs — LRU caches fill on pass 1."""
    n = len(names)
    times: List[float] = []
    for _ in range(PASSES):
        times.append(run_pass(fn, names))
    hot = times[1:]
    med = statistics.median(hot)
    print(f"  {label}")
    print(f"    pass 1 (cold): {times[0] * 1000:7.2f} ms   ({n / times[0]:>10,.0f} names/sec)")
    for i, t in enumerate(hot, 2):
        print(f"    pass {i} (hot ): {t * 1000:7.2f} ms   ({n / t:>10,.0f} names/sec)")
    print(f"    hot median:     {med * 1000:7.2f} ms   ({n / med:>10,.0f} names/sec)")


def main() -> None:
    names = load_names()
    admitted = [n for n in names if should_ascii(n)]
    rejected = [n for n in names if not should_ascii(n)]
    print(
        f"Corpus: {len(names)} total — "
        f"{len(admitted)} admitted, {len(rejected)} rejected"
    )
    print(f"Passes per run: {PASSES}")
    print()

    print(f"== COLD (cache-busted) — admitted bucket ({len(admitted)} names) ==")
    bench_cold("rigour maybe_ascii         ", maybe_ascii, admitted)
    bench_cold("normality ascii_text       ", normality_ascii, admitted)
    print()

    print(f"== COLD (cache-busted) — rejected bucket ({len(rejected)} names) ==")
    bench_cold("rigour maybe_ascii (identity) ", maybe_ascii, rejected)
    bench_cold("normality ascii_text (full)   ", normality_ascii, rejected)
    print()

    print(f"== HOT (cache-warm) — admitted bucket ({len(admitted)} names) ==")
    bench_hot("rigour maybe_ascii         ", maybe_ascii, admitted)
    bench_hot("normality ascii_text       ", normality_ascii, admitted)
    print()

    print(f"== HOT (cache-warm) — rejected bucket ({len(rejected)} names) ==")
    bench_hot("rigour maybe_ascii (identity) ", maybe_ascii, rejected)
    bench_hot("normality ascii_text (full)   ", normality_ascii, rejected)


if __name__ == "__main__":
    main()
