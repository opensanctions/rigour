import logging

import yaml

from genscripts.util import (
    CODE_PATH,
    RESOURCES_PATH,
    RUST_DATA_PATH,
    write_json,
    write_python,
)

log = logging.getLogger(__name__)

TEMPLATE = """
FORMS: dict[str, list[str]] = %r
"""


def generate_data_file() -> None:
    source_path = RESOURCES_PATH / "addresses"
    with open(source_path / "forms.yml", "r", encoding="utf-8") as ufh:
        data = yaml.safe_load(ufh.read())

    forms = data.get("forms", {})
    dest_path = CODE_PATH / "addresses" / "data.py"
    write_python(dest_path, TEMPLATE % forms)
    write_json(RUST_DATA_PATH / "addresses" / "forms.json", forms, indent=True)


if __name__ == "__main__":
    generate_data_file()
