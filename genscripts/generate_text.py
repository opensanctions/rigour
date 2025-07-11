import yaml
from typing import Dict
from genscripts.util import RESOURCES_PATH, CODE_PATH, write_python


ORDINALS_TEMPLATE = """
from typing import Dict, Tuple
"""


def generate_ordinals() -> None:
    ordinals_path = RESOURCES_PATH / "text" / "ordinals.yml"
    with open(ordinals_path, "r", encoding="utf-8") as ufh:
        ordinals_mapping: Dict[str, Dict[str, str]] = yaml.safe_load(ufh.read())

    mapping = {}
    for number, forms in ordinals_mapping["ordinals"].items():
        assert number is not None
        items = tuple(sorted(set([str(v) for v in forms if len(str(v)) > 0])))
        mapping[number] = items

    content = ORDINALS_TEMPLATE
    content += f"ORDINALS: Dict[int, Tuple[str, ...]] = {mapping!r}\n\n"
    out_path = CODE_PATH / "text" / "ordinals.py"
    write_python(out_path, content)


if __name__ == "__main__":
    generate_ordinals()
