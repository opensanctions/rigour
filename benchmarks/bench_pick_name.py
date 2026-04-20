"""Benchmark harness for `rigour.names.pick.pick_name`.

See `plans/rust-pick-name.md` for the port plan this measures.

Generates 100,000 synthetic pick cases with `k ~ U(1, 20)` candidates
per call, sampled from a pool of multi-script name clusters. Runs the
current Python implementation and — when available — the Rust-backed
implementation (`rigour._core.pick_name`), and reports per-impl
wall clock, ops/sec, ns/call, plus a 5,000-case parity check.

Run: `python benchmarks/bench_pick_name.py`
"""

from __future__ import annotations

import random
import time
from typing import Callable, List, Optional

from rigour.names.pick import _pick_name_python as py_pick_name
from rigour.names.pick import pick_name as rust_pick_name

# Realistic multi-script name clusters. Each inner list is one
# semantic identity across the scripts OpenSanctions actually sees on
# sanctioned persons. Mix is intentional: some clusters are
# Latin-dominated, others have more non-Latin entries.
NAME_CLUSTERS: List[List[str]] = [
    # Russian politicians — Latin + Cyrillic (rus/ukr) + CJK + Arabic
    [
        "Vladimir Putin", "Vladimir Vladimirovich Putin", "PUTIN Vladimir",
        "Владимир Путин", "Владимир Владимирович Путин", "ПУТИН Владимир",
        "Володимир Путін", "ПУТІН Володимир Володимирович",
        "ウラジーミル・プーチン", "弗拉基米尔·普京", "فلاديمير بوتين",
    ],
    [
        "Dmitry Medvedev", "Dmitri Medvedev", "MEDVEDEV Dmitry",
        "Дмитрий Медведев", "МЕДВЕДЕВ Дмитрий Анатольевич",
        "Дмитро Медведєв", "ديمتري ميدفيديف", "德米特里·梅德韦杰夫",
    ],
    # US politicians — Latin + Cyrillic transliterations + CJK
    [
        "Mitch McConnell", "Mitchell McConnell", "McCONNELL Mitch",
        "Митч Макконнелл", "Мітч Макконнелл", "ميتش ماكونيل",
        "ミッチ・マコーネル", "米奇·麥康諾", "미치 매코널",
    ],
    [
        "Joe Biden", "Joseph Biden", "Joseph R. Biden Jr.",
        "Джо Байден", "Джозеф Байден", "جو بايدن", "乔·拜登", "조 바이든",
    ],
    [
        "Donald Trump", "Donald J. Trump", "TRUMP Donald",
        "Дональд Трамп", "Дональд Трамп", "دونالد ترامب", "唐纳德·特朗普",
    ],
    # EU leaders
    [
        "Angela Merkel", "Angela Dorothea Merkel", "MERKEL Angela",
        "Ангела Меркель", "أنجيلا ميركل", "アンゲラ・メルケル", "安格拉·默克尔",
    ],
    [
        "Emmanuel Macron", "Emmanuel Jean-Michel Macron", "MACRON Emmanuel",
        "Эмманюэль Макрон", "إيمانويل ماكرون", "エマニュエル・マクロン",
        "埃马纽埃尔·马克龙",
    ],
    [
        "Ursula von der Leyen", "VON DER LEYEN Ursula",
        "Урсула фон дер Ляйен", "أورسولا فون دير لاين",
        "ウルズラ・フォン・デア・ライエン",
    ],
    # Middle East
    [
        "Abdel Fattah el-Sisi", "Abdul Fattah Saeed Hussein Khalil al-Sisi",
        "AL-SISI Abdel Fattah", "Абдул-Фаттах ас-Сиси", "عبد الفتاح السيسي",
    ],
    [
        "Bashar al-Assad", "Bashar Hafez al-Assad", "AL-ASSAD Bashar",
        "Башар Асад", "بشار الأسد", "バッシャール・アル＝アサド",
    ],
    # Asian leaders
    [
        "Xi Jinping", "XI Jinping",
        "Си Цзиньпин", "习近平", "シー・チンピン", "시진핑", "شي جين بينغ",
    ],
    [
        "Narendra Modi", "Narendra Damodardas Modi", "MODI Narendra",
        "Нарендра Моди", "ناريندرا مودي", "नरेन्द्र मोदी",
        "ナレンドラ・モディ", "나렌드라 모디",
    ],
    [
        "Shinzo Abe", "ABE Shinzo",
        "Синдзо Абэ", "شينزو آبي", "安倍晋三", "아베 신조",
    ],
    # Latin American
    [
        "Luiz Inacio Lula da Silva", "Luiz Inácio Lula da Silva",
        "LULA da Silva Luiz Inácio", "Лула да Силва",
        "لويس إيناسيو لولا دا سيلفا", "卢拉·达席尔瓦",
    ],
    [
        "Javier Milei", "Javier Gerardo Milei", "MILEI Javier",
        "Хавьер Милей", "خافيير ميلي", "ハビエル・ミレイ",
    ],
    # African
    [
        "Cyril Ramaphosa", "Matamela Cyril Ramaphosa", "RAMAPHOSA Cyril",
        "Сирил Рамафоса", "سيريل رامافوزا", "シリル・ラマポーザ",
    ],
    # Corporate / entity names (the common ORG case)
    [
        "Gazprom", "GAZPROM", "PAO Gazprom", "PAO \"Gazprom\"",
        "Газпром", "ПАО Газпром", "ПАО «Газпром»",
    ],
    [
        "Rosneft", "ROSNEFT", "NK Rosneft",
        "Роснефть", "ОАО Роснефть", "НК «Роснефть»",
    ],
    [
        "Sberbank", "SBERBANK", "Sberbank of Russia",
        "Сбербанк", "ПАО Сбербанк", "Сбербанк России", "ПАО «Сбербанк»",
    ],
    # Latin-only minor variants (common for Western names)
    ["Tim Cook", "Timothy Donald Cook", "COOK Tim", "Tim D. Cook"],
    ["Elon Musk", "Elon Reeve Musk", "MUSK Elon"],
    ["Jeff Bezos", "Jeffrey Bezos", "Jeffrey Preston Bezos", "BEZOS Jeff"],
    ["Mark Zuckerberg", "Mark Elliot Zuckerberg", "ZUCKERBERG Mark"],
    # Single-name edge cases
    ["Madonna"],
    ["Pele"],
]

# Heuristic mixes of clusters for case generation:
#   - 60% "typical": sample k candidates freely across one cluster
#   - 30% "latin-only": restrict to entries whose first char is ASCII
#   - 10% "non-latin": restrict to entries with no ASCII letters
TYPICAL = 0.60
LATIN_ONLY = 0.30
# NON_LATIN = remaining 10%


def _is_ascii_heavy(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isascii()) / len(letters) > 0.85


def _make_case(rng: random.Random) -> List[str]:
    cluster = rng.choice(NAME_CLUSTERS)
    k = rng.randint(1, 20)
    roll = rng.random()
    if roll < LATIN_ONLY:
        pool = [n for n in cluster if _is_ascii_heavy(n)]
    elif roll < LATIN_ONLY + (1.0 - LATIN_ONLY - TYPICAL):
        pool = [n for n in cluster if not _is_ascii_heavy(n)]
    else:
        pool = cluster
    if not pool:
        pool = cluster
    return [rng.choice(pool) for _ in range(k)]


def _generate_cases(seed: int, n: int) -> List[List[str]]:
    rng = random.Random(seed)
    return [_make_case(rng) for _ in range(n)]


def _run(
    impl: Callable[[List[str]], Optional[str]],
    cases: List[List[str]],
) -> tuple[float, int]:
    t0 = time.perf_counter()
    hits = 0
    for case in cases:
        result = impl(case)
        if result is not None:
            hits += 1
    return time.perf_counter() - t0, hits


def _format_row(label: str, seconds: float, n: int) -> str:
    per_call_us = (seconds * 1e6) / n
    per_sec = n / seconds
    return f"  {label:<25s} {seconds:7.3f}s total   {per_call_us:8.2f} µs/call   {per_sec:>10,.0f} picks/sec"


def _parity_check(cases: List[List[str]], py: Callable, rust: Callable) -> None:
    mismatches: List[tuple[List[str], Optional[str], Optional[str]]] = []
    for case in cases:
        a = py(case)
        b = rust(case)
        if a != b:
            mismatches.append((case, a, b))
    if mismatches:
        print(f"  PARITY FAIL: {len(mismatches)} / {len(cases)} mismatches")
        for case, a, b in mismatches[:5]:
            print(f"    in: {case!r}")
            print(f"    py:   {a!r}")
            print(f"    rust: {b!r}")
    else:
        print(f"  parity: {len(cases)} / {len(cases)} cases agree")


def main() -> None:
    N = 100_000
    SEED = 0xB1F  # arbitrary fixed seed for reproducibility
    cases = _generate_cases(SEED, N)

    # Distribution stats
    lengths = [len(c) for c in cases]
    avg = sum(lengths) / len(lengths)
    print(f"Generated {N:,} cases   (avg k={avg:.1f}, min={min(lengths)}, max={max(lengths)})")
    print()

    print("Python `pick_name`:")
    t_py, hits_py = _run(py_pick_name, cases)
    print(_format_row("rigour.names.pick_name", t_py, N))
    print(f"  non-None results: {hits_py:,} / {N:,}")

    print()
    print("Rust `pick_name`:")
    t_rust, hits_rust = _run(rust_pick_name, cases)
    print(_format_row("rigour._core.pick_name", t_rust, N))
    print(f"  non-None results: {hits_rust:,} / {N:,}")

    speedup = t_py / t_rust if t_rust > 0 else float("inf")
    print()
    print(f"Rust speedup: {speedup:.1f}×")

    print()
    print("Parity check on 5,000 random cases:")
    parity_cases = _generate_cases(SEED + 1, 5_000)
    _parity_check(parity_cases, py_pick_name, rust_pick_name)


if __name__ == "__main__":
    main()
