import csv
import yaml
from pathlib import Path

from followthemoney.types import registry

OUT_PATH = Path(__file__).parent.parent / "rigour" / "data" / "countries" / "world.yml"
GLEIF_JURIS = Path(__file__).parent / "data" / "gleif_acceptedjurisdictions_v1.5.csv"
OLD_WORLD = Path(__file__).parent / "data" / "world.yaml"
QID_FILE = Path(__file__).parent / "data" / "qids.csv"

TERR_DIR = Path(__file__).parent.parent / "rigour" / "data" / "territories" / "source"

if __name__ == "__main__":
    TERR_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "r") as fh:
        world = yaml.safe_load(fh.read())

    with open(GLEIF_JURIS, "r") as gfh:
        gfh.read(1)
        for row in csv.DictReader(gfh):
            code = row.pop("Code").lower()
            name = row.pop("Jurisdiction")
            type_ = row.pop("Type")

            jurisdiction = world.pop(code, {})
            if "name" not in jurisdiction:
                jurisdiction["name"] = name

            if type_ == "COUNTRY_ONLY":
                jurisdiction["is_country"] = True
                jurisdiction["is_jurisdiction"] = True
            if type_ == "COUNTRY_AND_SUBDIVISION":
                jurisdiction["is_country"] = False
                jurisdiction["is_jurisdiction"] = True
                jurisdiction["parent"] = code[:2]

            world[code] = jurisdiction

    with open(OLD_WORLD, "r") as ofh:
        old = yaml.safe_load(ofh.read())
        for code, desc in old.items():
            code = code.lower()

            cc = dict(world.pop(code, {}))
            if "name" not in cc:
                cc["name"] = desc.get("name")

            cc["is_country"] = cc.get("is_country", "-" not in code)
            cc["region"] = cc.get("region", desc.get("region"))
            cc["subregion"] = cc.get("subregion", desc.get("subregion"))
            cc["summary"] = cc.get("summary", desc.get("summary"))
            if cc["summary"] is None or len(cc["summary"]) == 0:
                cc.pop("summary")
            cc["summary"] = cc.get("summary", desc.get("wikipedia_intro"))
            cc["wikipedia_url"] = cc.get("wikipedia_url", desc.get("wikipedia_url"))
            if "see" in desc:
                cc["see"] = list(desc.get("see", []))

            world[code] = cc

    for code, cc in world.items():
        cc["full_name"] = cc.get("full_name", cc.get("name"))
        cc["is_ftm"] = registry.country.names.get(code) is not None
        summary = cc.get("summary")
        if summary is not None and len(summary):
            cc["summary"] = summary.strip()

        cc.pop("qid", None)
        cc.pop("other_qids", None)

        for k, v in list(cc.items()):
            if v is None or (isinstance(v, str) and not len(v)):
                cc.pop(k)

    with open(QID_FILE, "r") as qfh:
        csvreader = csv.DictReader(qfh)
        for row in csvreader:
            code = row.pop("value")
            qid = row.pop("original_value")
            if code in world:
                if "qid" not in world[code]:
                    world[code]["qid"] = qid
                else:
                    if "other_qids" not in world[code]:
                        world[code]["other_qids"] = []
                    if qid not in world[code]["other_qids"]:
                        world[code]["other_qids"].append(qid)
            else:
                print("XXXX", "MISSING", code)

    world.pop("xx", None)

    with open(OUT_PATH, "w") as wfh:
        yaml.dump(world, wfh, indent=2, allow_unicode=True, sort_keys=True)

    for code, cc in world.items():
        code_norm = code.replace("-", "_").lower()
        out = {
            "name": cc.pop("name"),
            "full_name": cc.pop("full_name"),
            "region": cc.pop("region", None),
            "subregion": cc.pop("subregion", None),
            "qid": cc.pop("qid", None),
            "other_qids": cc.pop("other_qids", None),
        }
        for k in cc.keys():
            out[k] = cc[k]
        for k, v in list(out.items()):
            if v is None:
                out.pop(k)
        out.pop("country", None)
        with open(TERR_DIR / f"{code_norm}.yml", "w") as tfh:
            yaml.dump(out, tfh, indent=2, allow_unicode=True, sort_keys=False)
