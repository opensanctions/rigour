from collections import Counter
import yaml
from typing import Dict, List
from normality import squash_spaces

from rigour.data.types import OrgTypeSpec
from genscripts.util import write_python, RESOURCES_PATH, CODE_PATH


DATA_TEMPLATE = """
from typing import Tuple, Dict
"""

ORG_TYPE_TEMPLATE = """
from typing import List
from rigour.data.types import OrgTypeSpec
"""


def generate_data_file() -> None:
    content = DATA_TEMPLATE

    stopwords_path = RESOURCES_PATH / "names" / "stopwords.yml"
    with open(stopwords_path, "r", encoding="utf-8") as ufh:
        stopword_lists: Dict[str, List[str]] = yaml.safe_load(ufh.read())

    for key, value in stopword_lists.items():
        values = tuple(sorted(set([str(v) for v in value if len(str(v)) > 0])))
        if isinstance(key, str):
            key = key.strip().upper()
        content += f"{key.upper()}: Tuple[str, ...] = {values!r}\n\n"

    symbols_path = RESOURCES_PATH / "names" / "symbols.yml"
    with open(symbols_path, "r", encoding="utf-8") as ufh:
        symbols_mappings: Dict[str, Dict[str, str]] = yaml.safe_load(ufh.read())

    for section, value in symbols_mappings.items():
        section = section.strip().upper()
        mapping = {}
        group_type = "str"
        # print(section, value)
        for group, items in value.items():
            if group is None:
                continue
            group_type = "int" if isinstance(group, int) else "str"
            if group_type == "str":
                group = group.strip().upper()
                if len(group) == 0:
                    continue
            items = tuple(sorted(set([str(v) for v in items if len(str(v)) > 0])))
            mapping[group] = items
        content += f"{section}: Dict[{group_type}, Tuple[str, ...]] = {mapping!r}\n\n"

    out_path = CODE_PATH / "names" / "data.py"
    write_python(out_path, content)


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
                display = squash_spaces(display)
                if len(display) > 0:
                    out["display"] = display
            generic = spec.get("generic")
            if generic is not None:
                generic = squash_spaces(generic)
                if len(generic) > 0:
                    out["generic"] = generic
            compare = spec.get("compare")
            if compare is not None:
                compare = squash_spaces(compare)
                out["compare"] = compare
            aliases_ = [squash_spaces(a) for a in spec.get("aliases", [])]
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


if __name__ == "__main__":
    generate_data_file()
    generate_org_type_file()
