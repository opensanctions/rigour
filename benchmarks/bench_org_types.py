#!/usr/bin/env python3
r"""Compare replace_org_types_compare: Python (regex.sub) vs Rust (Aho-Corasick).

Purpose: decide whether the Rust port should replace the Python
implementation outright. The Python path compiles a giant literal
alternation regex with lookaround anchors (`(?<!\w)X(?!\w)`). The
Rust path uses an Aho-Corasick automaton (see
`rust/src/names/matcher.rs`) plus a post-match boundary check, and
caches one automaton per `(normalize_flags, cleanup)` combination.

We measure three workloads:
  1. WARM — the same small realistic input called many times. Python
     has `@lru_cache(maxsize=1024)` on the wrapper; the Rust wrapper
     intentionally has none (Phase-5 direction — LRUs stay on the
     Python side where they do most good). This is the nomenklatura
     matching-loop shape: a few query names compared many times.
  2. COLD — every input unique (defeats Python's LRU). This is the
     yente-indexer shape: streaming through millions of distinct
     entity names once.
  3. CONSTRUCTION — how long does the Replacer take to build on first
     access? Relevant for short-lived CLI invocations.

Flags used: we run both sides with the **production** flag composition
(casefold only, matching nomenklatura/yente/FTM via
`prenormalize_name`). The old Python default (`_normalize_compare` =
squash+casefold) is also measurable by changing FLAGS below.

Run: `make develop` first (release build — debug is ~100x slower and
numbers are meaningless), then `python benchmarks/bench_org_types.py`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from rigour.names.org_types import replace_org_types_compare as py_impl
from rigour.names.org_types_rust import replace_org_types_compare as rs_impl
from rigour.names.tokenize import prenormalize_name
from rigour.text.normalize import Cleanup, Normalize

REPO_ROOT = Path(__file__).resolve().parent.parent

# Production flag composition — both implementations use this.
# Python's `prenormalize_name` ≡ str.casefold(). The Rust side takes
# the same composition as Normalize.CASEFOLD so the compiled alias
# set is built off casefolded needles on both sides.
FLAGS = Normalize.CASEFOLD
CLEANUP = Cleanup.Noop

# Python-side normaliser matching FLAGS above. For parity with what
# nomenklatura's logic_v2 passes today.
py_normalizer = prenormalize_name


def py_call(text: str) -> str:
    return py_impl(text, normalizer=py_normalizer)


def rs_call(text: str) -> str:
    return rs_impl(text, FLAGS, CLEANUP)


CORPUS: list[str] = [
    "Siemens Aktiengesellschaft",
    "Apple Inc.",
    "Bank of America Corporation",
    "ACME Limited Liability Company",
    "Gazprom Public Joint Stock Company",
    "Rosneft Oil Company",
    "ING Groep N.V.",
    "UniCredit S.p.A.",
    "China National Petroleum Corporation",
    "Deutsche Bank AG",
    "Volkswagen AG",
    "Credit Suisse Group AG",
    "BP p.l.c.",
    "Royal Dutch Shell plc",
    "Tesla Motors, Inc.",
    "John Spencer",
    "María García López",
    "Wang Xiaoming",
    "Владимир Путин",
    "招商银行股份有限公司",
    "AB Volvo",
    "Koninklijke Philips N.V.",
    "LUKOIL Oil Company",
    "IKEA Holding B.V.",
    "Tata Consultancy Services Limited",
    "GmbH & Co. KG Mueller",
    "Sberbank of Russia PJSC",
    "Tokyo Electric Power Company Holdings, Incorporated",
    "Fonds Commun de Placement à Risques",
    "Société Générale SA",
]


def _run_warm(fn, inputs, n_iters: int) -> float:
    start = time.perf_counter()
    for _ in range(n_iters):
        for f in inputs:
            fn(f)
    return time.perf_counter() - start


def _run_cold(fn, inputs, n_iters: int) -> float:
    start = time.perf_counter()
    for i in range(n_iters):
        for base in inputs:
            # Append a unique counter after a space so it's a separate
            # "word" and can't land inside an org-type alias.
            fn(f"{base} {i}")
    return time.perf_counter() - start


def _bench_construction() -> tuple[float, float]:
    import subprocess

    def measure(code: str) -> float:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(REPO_ROOT),
        )
        return float(result.stdout.strip())

    py_code = (
        "import time\n"
        "t = time.perf_counter()\n"
        "from rigour.names.org_types import replace_org_types_compare\n"
        "from rigour.names.tokenize import prenormalize_name\n"
        "replace_org_types_compare('acme llc', normalizer=prenormalize_name)\n"
        "print(time.perf_counter() - t)\n"
    )
    rs_code = (
        "import time\n"
        "t = time.perf_counter()\n"
        "from rigour.names.org_types_rust import replace_org_types_compare\n"
        "from rigour.text.normalize import Cleanup, Normalize\n"
        "replace_org_types_compare('acme llc', Normalize.CASEFOLD, Cleanup.Noop)\n"
        "print(time.perf_counter() - t)\n"
    )
    py_best = min(measure(py_code) for _ in range(3))
    rs_best = min(measure(rs_code) for _ in range(3))
    return py_best, rs_best


def _fmt(ns_per_call: float) -> str:
    if ns_per_call < 1_000:
        return f"{ns_per_call:7.1f} ns/call"
    if ns_per_call < 1_000_000:
        return f"{ns_per_call / 1_000:7.2f} µs/call"
    return f"{ns_per_call / 1_000_000:7.2f} ms/call"


def main() -> None:
    print(f"Corpus size: {len(CORPUS)} names")
    print(f"Flags: Python normalizer=prenormalize_name | Rust flags={FLAGS!r}")
    print()

    forms = [prenormalize_name(s) for s in CORPUS]

    # -------- Warm --------
    n_warm = 10_000
    # Warm both caches first so construction cost isn't in the hot loop.
    for f in forms:
        py_call(f)
        rs_call(f)
    py_t = _run_warm(py_call, forms, n_warm)
    rs_t = _run_warm(rs_call, forms, n_warm)
    total = n_warm * len(forms)
    py_per = py_t / total * 1e9
    rs_per = rs_t / total * 1e9
    print("=== WARM (Python has @lru_cache; Rust does not — match loop shape)")
    print(
        f"  python  {_fmt(py_per)}   total {py_t * 1000:7.1f} ms over {total} calls"
    )
    print(
        f"  rust    {_fmt(rs_per)}   total {rs_t * 1000:7.1f} ms over {total} calls"
    )
    print(f"  speedup {py_t / rs_t:5.2f}x (Rust wins if > 1.0)")
    print()

    # -------- Cold --------
    py_impl.cache_clear()  # type: ignore[attr-defined]
    n_cold = 5_000
    py_t = _run_cold(py_call, forms, n_cold)
    rs_t = _run_cold(rs_call, forms, n_cold)
    total = n_cold * len(forms)
    py_per = py_t / total * 1e9
    rs_per = rs_t / total * 1e9
    print("=== COLD (unique inputs; defeats Python LRU)")
    print(
        f"  python  {_fmt(py_per)}   total {py_t * 1000:7.1f} ms over {total} calls"
    )
    print(
        f"  rust    {_fmt(rs_per)}   total {rs_t * 1000:7.1f} ms over {total} calls"
    )
    print(f"  speedup {py_t / rs_t:5.2f}x (Rust wins if > 1.0)")
    print()

    # -------- Construction --------
    py_init, rs_init = _bench_construction()
    print("=== CONSTRUCTION (first-call, fresh Python process, best of 3)")
    print(f"  python  {py_init * 1000:6.1f} ms")
    print(f"  rust    {rs_init * 1000:6.1f} ms")
    print(f"  ratio   {py_init / rs_init:5.2f}x (Rust wins if > 1.0)")


if __name__ == "__main__":
    main()
