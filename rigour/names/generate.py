import yaml
from typing import Dict, List, Optional, Set, TypedDict
from normality import collapse_spaces

from rigour.data import DATA_PATH
from rigour.data.genutil import write_python


TEMPLATE = "from typing import List, Dict, Any\n\n"


class TypeSpec(TypedDict):
    display: Optional[str]
    compare: Optional[str]
    aliases: List[str]


def generate_data_file() -> None:
    names_path = DATA_PATH / "names"
    with open(names_path / "lists.yml", "r", encoding="utf-8") as ufh:
        lists: Dict[str, List[str]] = yaml.safe_load(ufh.read())

    content = TEMPLATE
    for key, value in lists.items():
        values = [str(v) for v in value if len(str(v)) > 0]
        content += f"{key.upper()}: List[str] = {values!r}\n"

    compare_forms: Set[str] = set()
    with open(names_path / "org_types.yml", "r", encoding="utf-8") as ofh:
        data: Dict[str, List[TypeSpec]] = yaml.safe_load(ofh.read())
        clean_types: List[TypeSpec] = []
        for spec in data.get("types", []):
            out: TypeSpec = {"display": None, "compare": None, "aliases": []}
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
            clean_types.append(out)
        content += f"ORG_TYPES: List[Dict[str, Any]] = {clean_types!r}\n"
        # print("Compare forms:", compare_forms)

    write_python(names_path / "data.py", content)


if __name__ == "__main__":
    generate_data_file()
