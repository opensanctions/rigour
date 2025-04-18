import yaml
from typing import Dict, List, Set
from normality import collapse_spaces

from rigour.data.types import OrgTypeSpec
from genscripts.util import write_python, RESOURCES_PATH, CODE_PATH


DATA_TEMPLATE = """
from typing import List
"""

ORG_TYPE_TEMPLATE = """
from typing import List
from rigour.data.types import OrgTypeSpec
"""


def generate_data_file() -> None:
    stopwords_path = RESOURCES_PATH / "names" / "stopwords.yml"
    with open(stopwords_path, "r", encoding="utf-8") as ufh:
        stopword_lists: Dict[str, List[str]] = yaml.safe_load(ufh.read())

    content = DATA_TEMPLATE
    for key, value in stopword_lists.items():
        values = [str(v) for v in value if len(str(v)) > 0]
        content += f"{key.upper()}: List[str] = {values!r}\n"

    out_path = CODE_PATH / "names" / "data.py"
    write_python(out_path, content)


def generate_org_type_file() -> None:
    content = ORG_TYPE_TEMPLATE
    compare_forms: Set[str] = set()
    types_path = RESOURCES_PATH / "names" / "org_types.yml"
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
            clean_types.append(out)
        content += f"ORG_TYPES: List[OrgTypeSpec] = {clean_types!r}\n"
        # print("Compare forms:", compare_forms)

    out_path = CODE_PATH / "names" / "org_types.py"
    write_python(out_path, content)


if __name__ == "__main__":
    generate_data_file()
    generate_org_type_file()
