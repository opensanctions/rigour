import yaml
from typing import Dict, List
from genscripts.util import RESOURCES_PATH, CODE_PATH, norm_string, write_python

ORDINALS_TEMPLATE = """
from typing import Dict, Tuple
"""

STOPWORDS_TEMPLATE = """
from typing import Tuple
"""


def generate_ordinals() -> None:
    ordinals_path = RESOURCES_PATH / "text" / "ordinals.yml"
    with open(ordinals_path, "r", encoding="utf-8") as ufh:
        ordinals_mapping: Dict[str, Dict[str, List[str]]] = yaml.safe_load(ufh.read())

    mapping = {}
    for number, forms in ordinals_mapping["ordinals"].items():
        assert number is not None
        forms = set(norm_string(v) for v in forms)
        items = tuple(sorted(set([v for v in forms if len(v) > 0])))
        mapping[number] = items

    content = ORDINALS_TEMPLATE
    content += f"ORDINALS: Dict[int, Tuple[str, ...]] = {mapping!r}\n\n"
    out_path = CODE_PATH / "text" / "ordinals.py"
    write_python(out_path, content)


def generate_stopwords() -> None:
    """Generate stopwords, nullwords, and nullplaces data from YAML."""
    content = STOPWORDS_TEMPLATE

    stopwords_path = RESOURCES_PATH / "text" / "stopwords.yml"
    with open(stopwords_path, "r", encoding="utf-8") as ufh:
        stopword_lists: Dict[str, List[str]] = yaml.safe_load(ufh.read())

    for key, value in stopword_lists.items():
        raw_values = [norm_string(v) for v in value]
        values = tuple(sorted(set(v for v in raw_values if len(v) > 0)))
        if isinstance(key, str):
            key = key.strip().upper()
        content += f"{key.upper()}: Tuple[str, ...] = {values!r}\n\n"

    out_path = CODE_PATH / "text" / "stopwords.py"
    write_python(out_path, content)


if __name__ == "__main__":
    generate_ordinals()
    generate_stopwords()
