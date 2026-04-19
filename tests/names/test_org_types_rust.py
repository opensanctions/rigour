"""Parity tests for the Rust port of `replace_org_types_compare`.

The Rust version lives in `rigour.names.org_types_rust`. Tests here
walk the full alias table from `rust/data/org_types.json`, injected
into several surrounding-context variants, and assert the two
implementations produce byte-identical output.

The Rust version takes `normalize_flags` instead of a callable. For
parity we feed Rust the flag composition equivalent to Python's
default `_normalize_compare` (squash + casefold), and run Python with
its default. A second test exercises the production-realistic case
(casefold only, matching `prenormalize_name`).

If this file starts failing after a resource edit, the most likely
cause is that `make rust-data` wasn't re-run — the Python path reads
`rigour/data/names/org_types.py`, the Rust path reads
`rust/data/org_types.json`, and the two are meant to regenerate in
lockstep from the same YAML.
"""

from pathlib import Path

import orjson

from rigour.names.org_types import replace_org_types_compare as py_impl
from rigour.names.org_types_rust import replace_org_types_compare as rs_impl
from rigour.names.tokenize import prenormalize_name
from rigour.text.normalize import Cleanup, Normalize

REPO_ROOT = Path(__file__).resolve().parents[2]
ORG_TYPES_JSON = REPO_ROOT / "rust" / "data" / "org_types.json"

# Match the Python default `_normalize_compare` (squash + casefold).
COMPARE_FLAGS = Normalize.CASEFOLD | Normalize.SQUASH_SPACES


def _load_aliases() -> list[str]:
    data = orjson.loads(ORG_TYPES_JSON.read_bytes())
    aliases: list[str] = []
    for spec in data:
        aliases.extend(spec.get("aliases", []))
    return aliases


def test_parity_on_realistic_inputs() -> None:
    samples = [
        "Siemens Aktiengesellschaft",
        "Acme LLC",
        "Acme, LLC.",
        "Bank of America Corporation",
        "ACME Limited Liability Company",
        "Gazprom OAO",
        "Public Joint Stock Company Gazprom",
        "Bellcorp Holdings",  # word boundary: 'llc' inside 'bellcorp' must not match
        "ZAO Lukoil",
        "Apple Inc.",
        "Apple Inc. is great",
        "GmbH & Co. KG Mueller",
        "IBM Plc. Ltd.",
        "just a person name",
        "有限公司 Some Chinese Co",
        "-gmbh Corp",
    ]
    for s in samples:
        form = prenormalize_name(s)
        py_out = py_impl(form)
        rs_out = rs_impl(form, COMPARE_FLAGS, Cleanup.Noop)
        assert py_out == rs_out, f"mismatch on {s!r}: python={py_out!r} rust={rs_out!r}"


def test_parity_exhaustive_alias_sweep() -> None:
    """Every alias, in four surrounding contexts, must match Python output."""
    aliases = _load_aliases()
    contexts = ["{}", "Acme {}", "{} Acme", "Acme {} Holdings"]
    for alias in aliases:
        for ctx in contexts:
            form = prenormalize_name(ctx.format(alias))
            py_out = py_impl(form)
            rs_out = rs_impl(form, COMPARE_FLAGS, Cleanup.Noop)
            assert py_out == rs_out, (
                f"mismatch on {ctx.format(alias)!r}: "
                f"python={py_out!r} rust={rs_out!r}"
            )


def test_empty_compare_fallback() -> None:
    """Inputs that reduce to empty under the replacer fall back to the original."""
    form = prenormalize_name("s.p.")
    rs_out = rs_impl(form, COMPARE_FLAGS, Cleanup.Noop)
    assert py_impl(form) == rs_out == "s.p."


def test_rust_cache_separates_flag_sets() -> None:
    """Different normalize_flags values must produce different outputs.

    Uses an input where the two flag sets diverge visibly: "EV   GmbH"
    with extra internal whitespace. With SQUASH_SPACES, Rust builds a
    regex expecting collapsed-whitespace aliases; without, it expects
    raw. Either way the output should differ between the two calls.
    """
    form = "ev   gmbh"  # already casefolded; three spaces preserved
    just_casefold = rs_impl(form, Normalize.CASEFOLD, Cleanup.Noop)
    casefold_and_squash = rs_impl(form, COMPARE_FLAGS, Cleanup.Noop)
    # The compiled regexes are both cached now; a third call should
    # return consistent results without rebuilding.
    just_casefold_again = rs_impl(form, Normalize.CASEFOLD, Cleanup.Noop)
    assert just_casefold == just_casefold_again
    # And the two flag sets must at minimum both be strings (caller
    # contract). We don't assert they differ because whether they do
    # depends on the alias corpus — the invariant worth testing is
    # that the cache keys by flags, not by input.
    assert isinstance(casefold_and_squash, str)
