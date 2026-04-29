"""compare_rust: full Python orchestration over rigour's Rust compare_parts.

Sibling of `compare_python` — same orchestration (analyze_names →
pair_symbols → tag_sort → residue → weight policies → aggregate),
just swaps the Python prototype `compare_parts_orig` for the Rust
`rigour._core.compare_parts`. The `qsv diff` between
`compare_python` and `compare_rust` per-case dumps is the parity
gate for the Rust port.
"""

from __future__ import annotations

from typing import List

from rigour._core import compare_parts as _rust_compare_parts

# Reuse the orchestration's Comparison adapter. The Rust call returns
# `rigour._core.Comparison` instances which expose `qps`, `rps`, `score`
# the same way the Python dataclass does — orchestration consumes them
# transparently.
from .compare_parts_orig import Comparison as _PyComparison
from .orchestration import compare_python_via  # injected below


# Adapter: call Rust, return a list with the same shape orchestration expects.
def _rust_residue(qry_parts, res_parts, fuzzy_tolerance=1.0) -> List[_PyComparison]:
    rust_results = _rust_compare_parts(list(qry_parts), list(res_parts), fuzzy_tolerance)
    out: List[_PyComparison] = []
    for r in rust_results:
        out.append(_PyComparison(qps=list(r.qps), rps=list(r.rps), score=r.score))
    return out


def compare_rust(name1: str, name2: str, schema: str) -> float:
    """Comparator: full orchestration with Rust residue function."""
    return compare_python_via(name1, name2, schema, residue_fn=_rust_residue)
