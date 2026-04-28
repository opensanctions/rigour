from collections import Counter
import yaml
from typing import Dict, List, Optional, TypedDict

from normality import squash_spaces

from genscripts.util import (
    norm_string,
    write_json,
    RESOURCES_PATH,
    RUST_DATA_PATH,
)


class OrgTypeSpec(TypedDict, total=False):
    """One org-type record. Inlined here since `rigour.data.types`
    (the previous home of this TypedDict) was retired when the
    Python tagger moved to Rust."""

    display: Optional[str]
    compare: Optional[str]
    generic: Optional[str]
    aliases: List[str]


def _sorted_unique_norm(values: List[str]) -> List[str]:
    """Normalise, dedupe, and sort a flat string list — stable JSON out."""
    return sorted({norm_string(v) for v in values if norm_string(v)})


def generate_name_stopwords_file() -> None:
    """Emit `rust/data/names/stopwords.json` — a five-field object of
    sorted de-duplicated normalised string lists. Consumed by the
    Rust-side `person_name_prefixes_list` / `org_name_prefixes_list` /
    `obj_name_prefixes_list` / `name_split_phrases_list` /
    `generic_person_names_list` accessors, which
    `rigour/names/{prefix,split_phrases,check}.py` read at import
    time."""
    stopwords_path = RESOURCES_PATH / "names" / "stopwords.yml"
    with open(stopwords_path, "r", encoding="utf-8") as ufh:
        name_data: Dict[str, List[str]] = yaml.safe_load(ufh.read())

    out_data: Dict[str, List[str]] = {}
    for key, value in name_data.items():
        # YAML section names arrive as SCREAMING_SNAKE_CASE; lower-case
        # them for serde-friendly snake_case field names on the Rust
        # side.
        out_data[key.strip().lower()] = _sorted_unique_norm(value)

    out_path = RUST_DATA_PATH / "names" / "stopwords.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, out_data, indent=True)


def generate_symbols_file() -> None:
    """Emit `rust/data/names/symbols.json` with the five nested-dict
    sections from `resources/names/symbols.yml` (`org_symbols`,
    `org_domains`, `person_symbols`, `person_nick`,
    `person_name_parts`). Consumed by the Rust tagger
    (`rust/src/names/symbols.rs`); no Python-side accessor — symbols
    are an internal detail of the tagger."""
    symbols_path = RESOURCES_PATH / "names" / "symbols.yml"
    with open(symbols_path, "r", encoding="utf-8") as ufh:
        symbols_mappings: Dict[str, Dict[str, str]] = yaml.safe_load(ufh.read())

    json_data: Dict[str, Dict[str, List[str]]] = {}

    for section, value in symbols_mappings.items():
        mapping: Dict[str, List[str]] = {}
        for group, items in value.items():
            if group is None:
                continue
            group_type_is_int = isinstance(group, int)
            if not group_type_is_int:
                group = norm_string(group).upper()
                if len(group) == 0:
                    continue
            values = set(norm_string(v) for v in items)
            sorted_values = sorted(v for v in values if len(v) > 0)
            mapping[str(group)] = sorted_values

        json_data[section.strip().lower()] = mapping

    rust_out = RUST_DATA_PATH / "names" / "symbols.json"
    rust_out.parent.mkdir(parents=True, exist_ok=True)
    write_json(rust_out, json_data, indent=True)


def generate_org_type_file() -> None:
    """Emit `rust/data/names/org_types.json` from `resources/names/org_types.yml`.

    Consumed by `rust/src/names/org_types.rs` (the Replacer + Rust
    tagger's ORG_CLASS symbol loop). No Python output — `rigour/data/
    names/org_types.py` was retired with the Python tagger in step 8.
    """
    types_path = RESOURCES_PATH / "names" / "org_types.yml"
    generic_types: Counter = Counter()
    with open(types_path, "r", encoding="utf-8") as ofh:
        data: Dict[str, List[OrgTypeSpec]] = yaml.safe_load(ofh.read())
        clean_types: List[OrgTypeSpec] = []
        for spec in data.get("types", []):
            out: OrgTypeSpec = {
                "display": None,
                "compare": None,
                "generic": None,
                "aliases": [],
            }
            display = spec.get("display", "")
            if display is not None:
                display = squash_spaces(norm_string(display))
                if len(display) > 0:
                    out["display"] = display
            generic = spec.get("generic")
            if generic is not None:
                generic = squash_spaces(norm_string(generic))
                if len(generic) > 0:
                    out["generic"] = generic
            compare = spec.get("compare")
            if compare is not None:
                compare = squash_spaces(norm_string(compare))
                out["compare"] = compare
            aliases_ = spec.get("aliases", [])
            aliases_ = [squash_spaces(norm_string(a)) for a in aliases_]
            aliases = [a for a in aliases_ if a is not None and len(a) > 0]
            if not len(aliases):
                print("No aliases for:", display)
                continue
            out["aliases"] = aliases
            if out["display"] is None:
                out.pop("display")
            if out["compare"] is None:
                out.pop("compare")
            if out["generic"] is None:
                out.pop("generic")
            else:
                generic_types.update([out["generic"]])
            clean_types.append(out)

    print("Compare types:")
    for k, v in generic_types.most_common():
        print(f"  {k}: {v}")

    write_json(RUST_DATA_PATH / "names" / "org_types.json", clean_types, indent=True)


def generate_compare_file() -> None:
    """Emit `rust/data/names/compare.json` from `resources/names/compare.yml`.

    Currently holds the visual/phonetic confusable pair table used by
    the cost-folded DP in the future Rust `compare_parts` (see
    `plans/weighted-distance.md`). Each pair is emitted in both
    directions, sorted, so the Rust loader does a single `binary_search`
    per char-pair lookup with no per-call expansion.

    No Python output — the harness's Python prototype keeps an inline
    mirror; it retires once the Rust port hits parity.
    """
    compare_path = RESOURCES_PATH / "names" / "compare.yml"
    with open(compare_path, "r", encoding="utf-8") as fh:
        data: Dict[str, List[List[str]]] = yaml.safe_load(fh.read())

    similar_pairs = data.get("similar_pairs", [])
    expanded: set = set()
    for pair in similar_pairs:
        if len(pair) != 2:
            raise ValueError(f"similar_pairs entry must be a 2-element list, got {pair!r}")
        a, b = pair
        if len(a) != 1 or len(b) != 1:
            raise ValueError(f"similar_pairs entries must be single chars, got {pair!r}")
        expanded.add((a, b))
        expanded.add((b, a))

    out_data = {
        "similar_pairs": sorted([list(p) for p in expanded]),
    }

    out_path = RUST_DATA_PATH / "names" / "compare.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, out_data, indent=True)


if __name__ == "__main__":
    generate_name_stopwords_file()
    generate_symbols_file()
    generate_org_type_file()
    generate_compare_file()
