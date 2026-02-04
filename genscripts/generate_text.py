import sys
import yaml
import unicodedata
from typing import Dict, List, Set, Tuple
from genscripts.util import RESOURCES_PATH, CODE_PATH, norm_string, write_python

IGNORE_SCRIPTS = {"Common", "Inherited"}
LATINIZABLE = (
    "Cyrillic",
    "Greek",
    "Latin",
)  # Wider set is defined in rigour.text.scripts via a fallback

ORDINALS_TEMPLATE = """
from typing import Dict, Tuple
"""

SCRIPTS_TEMPLATE = """
from typing import Set, Dict, Tuple
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


def generate_script_data() -> None:
    """Generate the unicode script data."""
    script_path = RESOURCES_PATH / "text" / "scripts.txt"
    scripts = set()

    ranges: Dict[Tuple[int, int], str] = {}
    latin_chars: Set[int] = set()
    latinizable_chars: Set[int] = set()

    prev_script: str = ""
    prev_range: Tuple[int, int] = (0, 0)
    min_non_latin = 0xFFFFF
    with open(script_path, "r", encoding="utf-8") as sfh:
        while line := sfh.readline():
            if line.startswith("#") or not line.strip():
                continue
            line = line.split("#")[0]
            cprange, script = line.split(";")
            min_cp, max_cp = cprange, cprange
            if ".." in cprange:
                min_cp, max_cp = cprange.split("..")
            min_cp = int(min_cp, 16)
            max_cp = int(max_cp, 16)
            script = sys.intern(script.strip())
            if script in IGNORE_SCRIPTS:
                continue
            scripts.add(script)

            if script != "Latin":
                min_non_latin = min(min_non_latin, min_cp)

            for cp in range(min_cp, max_cp + 1):
                ch = chr(cp)
                cat = sys.intern(unicodedata.category(ch))
                if cat.startswith("L") or cat.startswith("N"):
                    if script == "Latin" and cat.startswith("N"):
                        # Latin numbers are pretty universally used
                        continue
                    if script == "Latin":
                        latin_chars.add(cp)
                    if script in LATINIZABLE:
                        latinizable_chars.add(cp)

            if script == prev_script and min_cp == prev_range[1] + 1:
                # extend the previous range
                min_cp = prev_range[0]
                ranges.pop(prev_range)

            ranges[(min_cp, max_cp)] = script
            prev_script = script
            prev_range = (min_cp, max_cp)

    content = SCRIPTS_TEMPLATE
    content += "RANGES: Dict[Tuple[int, int], str] = {}\n\n".format(ranges)
    content += "LATIN_CHARS: Set[int] = {}  # fmt: skip \n\n".format(latin_chars)
    content += "LATINIZABLE_CHARS: Set[int] = {}  # fmt: skip \n\n".format(
        latinizable_chars
    )
    out_path = CODE_PATH / "text" / "scripts.py"
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
    generate_script_data()
    generate_stopwords()
