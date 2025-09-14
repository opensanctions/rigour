import os
import yaml
import logging
from typing import Any, Dict, Set

from rigour.ids.wikidata import is_qid
from rigour.territories.territory import Territory
from rigour.territories.util import clean_code, clean_codes
from genscripts.util import write_jsonl, norm_string, RESOURCES_PATH, CODE_PATH

log = logging.getLogger(__name__)

TEMPLATE = """from typing import Dict, Any

TERRITORIES: Dict[str, Any] = %r
"""


def update_data() -> None:
    countries_dir = RESOURCES_PATH / "territories"
    path = os.path.dirname(__file__)
    raw_territories: Dict[str, Any] = {}
    territories: Dict[str, Territory] = {}
    seen_codes: Set[str] = set()
    for filename in os.listdir(countries_dir):
        if not filename.endswith(".yml"):
            continue
        source_file = os.path.join(path, countries_dir / filename)
        code = clean_code(filename.replace(".yml", ""))
        if code in seen_codes:
            print(f"Duplicate code: {code}")
            continue
        seen_codes.add(code)
        with open(source_file, "r", encoding="utf-8") as ufh:
            data = yaml.safe_load(ufh.read())
            data["code"] = norm_string(code)
            data["name"] = norm_string(data["name"])
            if "full_name" in data:
                data["full_name"] = norm_string(data["full_name"])
            if "region" in data:
                data["region"] = norm_string(data["region"])
            if "subregion" in data:
                data["subregion"] = norm_string(data["subregion"])
            if "names_strong" in data:
                names = set(norm_string(name) for name in data["names_strong"])
                data["names_strong"] = sorted(names)
            if "names_weak" in data:
                names = set(norm_string(name) for name in data["names_weak"])
                data["names_weak"] = sorted(names)
            raw_territories[code] = data
            data["other_codes"] = clean_codes(data.get("other_codes", []))
            for other in data["other_codes"]:
                if other in territories:
                    log.warning("Duplicate code: %s", other)
            if len(data["other_codes"]) == 0:
                data.pop("other_codes")
            data["see"] = clean_codes(data.get("see", []))
            if len(data["see"]) == 0:
                data.pop("see")

            territories[code] = Territory(territories, code, data)

    for terr in territories.values():
        assert terr.name is not None, f"Must have a name: {terr.code}"
        assert terr.code is not None, f"Missing code: {terr.name}"
        assert terr.qid is not None, f"Missing QID: {terr.code}"
        assert is_qid(terr.qid), f"Invalid QID: {terr.code}"
        for other_qid in terr.other_qids:
            assert is_qid(other_qid), f"Invalid QID: {other_qid}"
        if terr._parent is not None:
            assert terr._parent != terr.code, f"Cannot be its own parent: {terr.code}"
            if terr._parent not in territories:
                msg = "Invalid parent: %s (country: %r)" % (terr._parent, terr.code)
                raise RuntimeError(msg)

        for successor in terr._successors:
            if successor not in territories:
                msg = "Invalid successor: %s (country: %r)" % (successor, terr.code)
                raise RuntimeError(msg)

        for see in terr._see:
            if see not in territories:
                msg = "Invalid see: %s (country: %r)" % (see, terr.code)
                raise RuntimeError(msg)

        if terr.is_country and not terr.is_jurisdiction:
            msg = "Country is not a jurisdiction: %r" % terr.code
            raise RuntimeError(msg)

    out_path = CODE_PATH / "territories" / "data.jsonl"
    write_jsonl(out_path, raw_territories.values())


if __name__ == "__main__":
    update_data()
