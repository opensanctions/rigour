import logging

import yaml

from genscripts.util import CODE_PATH, RESOURCES_PATH, write_python

log = logging.getLogger(__name__)

TEMPLATE = """
FORMS: dict[str, list[str]] = %r
"""


def generate_data_file() -> None:
    source_path = RESOURCES_PATH / "addresses"
    with open(source_path / "forms.yml", "r", encoding="utf-8") as ufh:
        data = yaml.safe_load(ufh.read())

    dest_path = CODE_PATH / "addresses" / "data.py"
    content = TEMPLATE % data.get("forms", {})
    write_python(dest_path, content)


if __name__ == "__main__":
    generate_data_file()
