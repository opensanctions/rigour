import os
import csv
import logging

from rigour.data import DATA_PATH
from rigour.data.genutil import write_python
from rigour.langs.util import normalize_code

# https://iso639-3.sil.org/sites/iso639-3/files/downloads/iso-639-3.tab
log = logging.getLogger(__name__)

TEMPLATE = """from typing import Dict, Set

ISO3_ALL: Set[str] = set(%r)  # noqa
ISO3_MAP: Dict[str, str] = %r  # noqa
ISO2_MAP: Dict[str, str] = %r  # noqa
"""


def update_data() -> None:
    iso3_ids = set()
    iso2_map = {}
    iso3_map = {}

    lang_path = DATA_PATH / "langs"
    path = os.path.dirname(__file__)
    source_file = os.path.join(path, lang_path / "iso-639-3.tab")
    with open(source_file, "r", encoding="utf-8") as ufh:
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

    # Hack in some outdated/extra aliases:
    iso3_map.update(
        {
            "mo": "ron",
            "mol": "ron",
            "scc": "srp",
            "scr": "hrv",
            "jw": "jav",
            "jv": "jav",
            "jaw": "jav",
            "iw": "heb",
            "in": "ind",
            "ji": "yid",
        }
    )

    content = TEMPLATE % (list(sorted(iso3_ids)), iso3_map, iso2_map)
    write_python(lang_path / "iso639.py", content)


if __name__ == "__main__":
    update_data()
