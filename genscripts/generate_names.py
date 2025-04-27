from collections import Counter
import yaml
from typing import Dict, List, Set
from normality import collapse_spaces

from rigour.data.types import OrgTypeSpec
from genscripts.util import write_python, RESOURCES_PATH, CODE_PATH


DATA_TEMPLATE = """
from typing import List, Dict
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
        values = [str(v) for v in value if len(str(v)) > 0]
        content += f"{key.upper()}: List[str] = {values!r}\n\n"

    symbols_path = RESOURCES_PATH / "names" / "symbols.yml"
    with open(symbols_path, "r", encoding="utf-8") as ufh:
        symbols_mappings: Dict[str, Dict[str, str]] = yaml.safe_load(ufh.read())

    for key, value in symbols_mappings.items():
        mapping = {}
        for group, items in value.items():
            if group is None or len(group) == 0:
                continue
            items = sorted(set([str(v) for v in items if len(str(v)) > 0]))
            mapping[group] = items
        content += f"{key.upper()}: Dict[str, List[str]] = {mapping!r}\n\n"

    out_path = CODE_PATH / "names" / "data.py"
    write_python(out_path, content)


def generate_org_type_file() -> None:
    content = ORG_TYPE_TEMPLATE
    compare_forms: Set[str] = set()
    types_path = RESOURCES_PATH / "names" / "org_types.yml"
    compare_types = Counter()
    with open(types_path, "r", encoding="utf-8") as ofh:
        data: Dict[str, List[OrgTypeSpec]] = yaml.safe_load(ofh.read())
        clean_types: List[OrgTypeSpec] = []
        for spec in data.get("types", []):
            out: OrgTypeSpec = {"display": None, "compare": None, "aliases": []}
            display = collapse_spaces(spec.get("display", ""))
            if display is not None and len(display) > 0:
                out["display"] = display
            compare = collapse_spaces(spec.get("compare", ""))
            if compare is not None and len(compare) > 0:
                out["compare"] = compare
                compare_forms.add(compare)
            aliases_ = [collapse_spaces(a) for a in spec.get("aliases", [])]
            aliases = [a for a in aliases_ if a is not None and len(a) > 0]
            if not len(aliases):
                print("No aliases for:", display)
                continue
            out["aliases"] = aliases
            if out["display"] is None:
                out.pop("display")
            if out["compare"] is None:
                out.pop("compare")
            else:
                compare_types.update([out["compare"]])
            clean_types.append(out)
        content += f"ORG_TYPES: List[OrgTypeSpec] = {clean_types!r}\n"

    print("Compare types:")
    for k, v in compare_types.most_common():
        print(f"  {k}: {v}")

    out_path = CODE_PATH / "names" / "org_types.py"
    write_python(out_path, content)


if __name__ == "__main__":
    generate_data_file()
    generate_org_type_file()
