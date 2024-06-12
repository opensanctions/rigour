import csv
import yaml
from pathlib import Path

OUT_PATH = Path(__file__).parent.parent / "rigour" / "data" / "countries" / "world.yml"
GLEIF_JURIS = Path(__file__).parent / "data" / "gleif_acceptedjurisdictions_v1.5.csv"
OLD_WORLD = Path(__file__).parent / "data" / "world.yaml"

if __name__ == "__main__":
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
                jurisdiction["country"] = True
            if type_ == "COUNTRY_AND_SUBDIVISION":
                jurisdiction["country"] = False
                jurisdiction["parent"] = code[:2]

            world[code] = jurisdiction

    with open(OLD_WORLD, 'r') as ofh:
        old = yaml.safe_load(ofh.read())
        for code, desc in old.items():
            code = code.lower()

            cc = dict(world.pop(code, {}))
            if "name" not in cc:
                cc["name"] = desc.get('name')

            cc['country'] = cc.get('country', '-' not in code)
            cc['region'] = cc.get('region', desc.get('region'))
            cc['subregion'] = cc.get('subregion', desc.get('subregion'))
            cc['summary'] = cc.get('summary', desc.get('summary'))
            if cc['summary'] is None or len(cc['summary']) == 0:
                cc.pop('summary')
            cc['summary'] = cc.get('summary', desc.get('wikipedia_intro'))
            cc['wikipedia_url'] = cc.get('wikipedia_url', desc.get('wikipedia_url'))
            if 'see' in desc:
                cc["see"] = list(desc.get('see', []))

            world[code] = cc

    for code, cc in world.items():
        cc['full_name'] = cc.get('full_name', cc.get('name'))
        summary = cc.get('summary')
        if summary is not None and len(summary):
            cc['summary'] = summary.strip()

        for k, v in list(cc.items()):
            if v is None or (isinstance(v, str) and not len(v)):
                cc.pop(k)

    world.pop('xx', None)

    # with open(OUT_PATH, "w") as wfh:
    #     yaml.dump(world, wfh, indent=2, allow_unicode=True, sort_keys=True)
