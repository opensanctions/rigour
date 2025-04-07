import yaml
from typing import Any, Dict, List, Set
from normality import collapse_spaces

from rigour.data import DATA_PATH
from rigour.data.genutil import write_python


TEMPLATE = "from typing import List, Dict, Any\n\n"


def generate_data_file() -> None:
    names_path = DATA_PATH / "names"
    with open(names_path / "lists.yml", "r", encoding="utf-8") as ufh:
        data: Dict[str, List[str]] = yaml.safe_load(ufh.read())

    content = TEMPLATE
    for key, value in data.items():
        values = [str(v) for v in value if len(str(v)) > 0]
        content += f"{key.upper()}: List[str] = {values!r}\n"

    compare_forms: Set[str] = set()
    with open(names_path / "org_types.yml", "r", encoding="utf-8") as ofh:
        data: Dict[str, List[Dict[str, Any]]] = yaml.safe_load(ofh.read())
        types = data.get("types", {})
        clean_types = []
        for spec in types:
            out = {}
            display = collapse_spaces(spec.pop("display", ""))
            if display is not None and len(display) > 0:
                out["display"] = display
            compare = collapse_spaces(spec.pop("compare", ""))
            if compare is not None and len(compare) > 0:
                out["compare"] = compare
                compare_forms.add(compare)
            aliases = [collapse_spaces(a) for a in spec.pop("aliases", [])]
            aliases = [a for a in aliases if a is not None and len(a) > 0]
            if not len(aliases):
                print("No aliases for:", display)
                continue
            out["aliases"] = aliases
            if len(spec):
                print("Extra keys in org_types.yml:", spec)
            clean_types.append(out)
        content += f"ORG_TYPES: List[Dict[str, Any]] = {clean_types!r}\n"
        # print("Compare forms:", compare_forms)

    write_python(names_path / "data.py", content)


if __name__ == "__main__":
    generate_data_file()
