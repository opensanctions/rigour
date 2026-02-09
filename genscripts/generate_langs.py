import csv
import logging
from typing import Dict, Set

import yaml

from rigour.langs.util import normalize_code
from genscripts.util import write_python, CODE_PATH, RESOURCES_PATH

# https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab
log = logging.getLogger(__name__)

TEMPLATE = """from typing import Dict, Set

ISO3_ALL: Set[str] = set(%r)  # noqa
ISO3_MAP: Dict[str, str] = %r  # noqa
ISO2_MAP: Dict[str, str] = %r  # noqa
"""


def update_data() -> None:
    iso3_ids: Set[str] = set()
    iso2_map: Dict[str, str] = {}
    iso3_map = {}

    source_path = RESOURCES_PATH / "langs" / "iso-639-3.tab"
    with open(source_path, "r", encoding="utf-8") as ufh:
        for row in csv.DictReader(ufh, delimiter="\t"):
            iso3 = normalize_code(row.pop("Id"))
            if iso3 is None or len(iso3) != 3:
                continue
            iso3_ids.add(iso3)

            part1 = normalize_code(row.pop("Part1"))
            if part1 is not None:
                iso3_map[part1] = iso3
                iso2_map[iso3] = part1

            part2b = normalize_code(row.pop("Part2B"))
            if part2b is not None:
                iso3_map[part2b] = iso3

            part2t = normalize_code(row.pop("Part2T"))
            if part2t is not None:
                iso3_map[part2t] = iso3

            ref_name = normalize_code(row.pop("Ref_Name"))
            if ref_name is not None and len(ref_name) > 3:
                iso3_map[ref_name] = iso3

    names_path = RESOURCES_PATH / "langs" / "names.yaml"
    with open(names_path, "r", encoding="utf-8") as nfh:
        mapping = yaml.safe_load(nfh)
        for code, values in mapping["langs"].items():
            iso3 = normalize_code(code)
            if iso3 not in iso3_ids:
                log.warning("Code %r from names.yaml not found in iso-639-3.tab", code)
                continue
            for value in values:
                iso3_map[value.lower()] = iso3

    output_path = CODE_PATH / "langs" / "iso639.py"
    content = TEMPLATE % (list(sorted(iso3_ids)), iso3_map, iso2_map)
    write_python(output_path, content)


if __name__ == "__main__":
    update_data()
