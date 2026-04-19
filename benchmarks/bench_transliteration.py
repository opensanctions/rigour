#!/usr/bin/env python3
"""Compare transliteration speed: rigour (Rust/ICU4X) vs normality (PyICU).

Goal: detect regressions relative to the PyICU baseline we migrated away
from. We don't expect a speedup — the MVP thesis is that per-call FFI
overhead doesn't amortise for isolated calls. This benchmark keeps us
honest about the regression surface.

Both functions have LRU caches at the Python wrapper level. We defeat
those by generating unique inputs per iteration so we measure the actual
transliteration path rather than cache lookup.

Run: `make bench` (equivalent to `python benchmarks/bench_transliteration.py`).

IMPORTANT: the ICU4X transliteration code is trie- and loop-heavy. A debug
build runs ~100x slower than release and produces nonsense numbers. Ensure
the extension was built via `make develop` (release) before running —
`make develop-debug` is only for code-iteration, not perf measurement.
"""
from __future__ import annotations

import time
from typing import Callable, List, Tuple

from normality import ascii_text as normality_ascii
from normality import latinize_text as normality_latinize
from rigour._core import _ffi_noop as rigour_ffi_noop  # baseline PyO3 cost
from rigour.text.transliteration import ascii_text as rigour_ascii
from rigour.text.transliteration import latinize_text as rigour_latinize


CORPUS: List[Tuple[str, str]] = [
    ("ascii", "John Spencer"),
    ("latin_diacritics", "François Müller"),
    ("cyrillic_short", "Владимир Путин"),
    ("cyrillic_long", "Владимир Владимирович Путин"),
    ("chinese", "招商银行有限公司"),
    ("greek", "Κυριάκος Μητσοτάκης"),
    ("arabic", "محمد بن سلمان آل سعود"),
    ("armenian", "Միթչել Մակքոնել"),
    ("georgian", "მიხეილ სააკაშვილი"),
    ("korean", "김민석 박근혜"),
    ("japanese", "ウラジーミル・プーチン"),
    ("mixed_two", "Hello мир"),
    ("mixed_three", "Hello мир 中国"),
]

ITERS = 1000


def bench(fn: Callable[[str], str], inp: str, iters: int = ITERS) -> float:
    """Average nanoseconds per call over `iters` unique inputs (cache-busted)."""
    # Unique inputs defeat the @lru_cache on both wrappers.
    unique = [f"{inp} {i}" for i in range(iters)]
    # Warm up once to trigger any lazy thread-local init.
    fn(inp)
    start = time.perf_counter_ns()
    for s in unique:
        fn(s)
    elapsed = time.perf_counter_ns() - start
    return elapsed / iters


def fmt_ns(ns: float) -> str:
    if ns < 1_000:
        return f"{ns:.0f} ns"
    if ns < 1_000_000:
        return f"{ns / 1_000:.2f} µs"
    return f"{ns / 1_000_000:.2f} ms"


def main() -> None:
    # PyO3 FFI baseline: a no-op Rust function that takes a str and returns
    # it unchanged. This is the floor cost we pay per call even if the
    # underlying Rust work is zero.
    print("== PyO3 FFI baseline (String-in, String-out, zero work) ==")
    print(f"{'Input':<20} {'ffi_noop':>12}")
    print("-" * 34)
    for label, inp in CORPUS:
        ffi_ns = bench(rigour_ffi_noop, inp)
        print(f"{label:<20} {fmt_ns(ffi_ns):>12}")

    pairs: List[Tuple[str, Callable[[str], str], Callable[[str], str]]] = [
        ("ascii_text", normality_ascii, rigour_ascii),
        ("latinize_text", normality_latinize, rigour_latinize),
    ]
    for fn_label, n_fn, r_fn in pairs:
        print(f"\n== {fn_label} ==")
        print(
            f"{'Input':<20} {'normality':>12} {'rigour':>12} {'ratio':>8} "
            f"{'rigour-ffi':>12}"
        )
        print("-" * 70)
        for label, inp in CORPUS:
            n_ns = bench(n_fn, inp)
            r_ns = bench(r_fn, inp)
            ffi_ns = bench(rigour_ffi_noop, inp)
            ratio = r_ns / n_ns if n_ns > 0 else float("inf")
            # rigour minus the FFI floor = pure library work in Rust.
            r_library = max(0.0, r_ns - ffi_ns)
            print(
                f"{label:<20} {fmt_ns(n_ns):>12} {fmt_ns(r_ns):>12} "
                f"{ratio:>7.2f}x {fmt_ns(r_library):>12}"
            )


if __name__ == "__main__":
    main()
