from collections import Counter
import yaml
from typing import Dict, List
from normality import squash_spaces

from rigour.data.types import OrgTypeSpec
from genscripts.util import (
    norm_string,
    write_python,
    write_json,
    RESOURCES_PATH,
    CODE_PATH,
    RUST_DATA_PATH,
)


DATA_TEMPLATE = """
from typing import Tuple, Dict
"""

ORG_TYPE_TEMPLATE = """
from typing import List
from rigour.data.types import OrgTypeSpec
"""


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
    write_json(out_path, out_data)


def generate_symbols_data_file() -> None:
    """Emit two artifacts from the one YAML source:

    * `rigour/data/names/data.py` — five UPPERCASE module constants
      (`ORG_SYMBOLS`, `ORG_DOMAINS`, `PERSON_SYMBOLS`, `PERSON_NICK`,
      `PERSON_NAME_PARTS`) consumed by the Python tagger today.
      Retired in step 8 of `plans/rust-tagger.md` when the tagger
      itself ports to Rust.
    * `rust/data/names/symbols.json` — same data under five
      lowercase top-level keys. Rust-only artifact; the future
      tagger in `rust/src/names/tagger.rs` reads it via
      `include_str!`. No Python-facing accessor (per
      `rust-tagger.md`'s Rust-only classification for this file).

    Both are built from the same in-memory structure so they can't
    drift."""
    symbols_path = RESOURCES_PATH / "names" / "symbols.yml"
    with open(symbols_path, "r", encoding="utf-8") as ufh:
        symbols_mappings: Dict[str, Dict[str, str]] = yaml.safe_load(ufh.read())

    content = DATA_TEMPLATE
    json_data: Dict[str, Dict[str, List[str]]] = {}

    for section, value in symbols_mappings.items():
        section_upper = section.strip().upper()
        mapping = {}
        group_type = "str"
        for group, items in value.items():
            if group is None:
                continue
            group_type = "int" if isinstance(group, int) else "str"
            if group_type == "str":
                group = norm_string(group).upper()
                if len(group) == 0:
                    continue
            values = set(norm_string(v) for v in items)
            items = tuple(sorted(v for v in values if len(v) > 0))
            mapping[group] = items
        content += f"{section_upper}: Dict[{group_type}, Tuple[str, ...]] = {mapping!r}\n\n"

        # Mirror into the Rust-side JSON. Keys stay lowercase here —
        # Python callers that want uppercase read from data.py. The
        # Rust consumer handles its own casing policy when building
        # the tagger.
        json_data[section.strip().lower()] = {
            str(k): list(v) for k, v in mapping.items()
        }

    out_path = CODE_PATH / "names" / "data.py"
    write_python(out_path, content)

    rust_out = RUST_DATA_PATH / "names" / "symbols.json"
    rust_out.parent.mkdir(parents=True, exist_ok=True)
    write_json(rust_out, json_data)


def generate_org_type_file() -> None:
    content = ORG_TYPE_TEMPLATE
    types_path = RESOURCES_PATH / "names" / "org_types.yml"
    generic_types = Counter()
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
        content += f"ORG_TYPES: List[OrgTypeSpec] = {clean_types!r}\n"

    print("Compare types:")
    for k, v in generic_types.most_common():
        print(f"  {k}: {v}")

    out_path = CODE_PATH / "names" / "org_types.py"
    write_python(out_path, content)

    # Rust-side artifact — same in-memory list, JSON-encoded. Consumed
    # by `rust/src/names/org_types.rs`.
    write_json(RUST_DATA_PATH / "org_types.json", clean_types)


if __name__ == "__main__":
    generate_name_stopwords_file()
    generate_symbols_data_file()
    generate_org_type_file()
