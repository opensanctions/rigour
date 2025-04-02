import yaml
import logging

from rigour.data import DATA_PATH
from rigour.data.genutil import write_python

log = logging.getLogger(__name__)

TEMPLATE = """
from typing import Dict, List

NORMALISATIONS: Dict[str, List[str]] = %r
"""


def generate_data_file() -> None:
    addr_path = DATA_PATH / "addresses"
    with open(addr_path / "norms.yml", "r", encoding="utf-8") as ufh:
        data = yaml.safe_load(ufh.read())

    content = TEMPLATE % data.get("normalizations", {})
    write_python(addr_path / "data.py", content)


if __name__ == "__main__":
    generate_data_file()
