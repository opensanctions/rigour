import sys
import requests
import yaml
from pathlib import Path

from rigour.territories import get_territory

TERR_DIR = Path(__file__).parent.parent / "rigour" / "data" / "territories" / "source"
WD_API = "https://www.wikidata.org/w/api.php"


def fetch_territory(qid: str, code: str) -> None:
    code = code.lower().replace("-", "_")
    parent = code.split("_")[0]
    path = TERR_DIR / f"{code}.yml"
    if path.exists():
        print("Already exists:", path.as_posix())
        return
    params = {"format": "json", "ids": qid, "action": "wbgetentities"}
    response = requests.get(WD_API, params=params)
    data = response.json()
    entity = data.get("entities", {}).get(qid)
    if entity is None:
        return
    labels = entity.get("labels", {})
    name = labels["en"]["value"]
    data = {
        "name": name,
        "qid": qid,
        "is_country": False,
        "is_historical": False,
        "is_jurisdiction": True,
        "is_ftm": False,
    }
    if parent != code and len(parent):
        parent_terr = get_territory(parent)
        if parent_terr is not None:
            data["parent"] = parent
            data["full_name"] = f"{name} ({parent_terr.name})"
    else:
        data["full_name"] = name

    # Extract second ISO 3166-2 code from Wikidata (P300 - external ID)
    claims = entity.get("claims", {})
    iso_codes = []
    if "P300" in claims:
        for statement in claims["P300"]:
            mainsnak = statement.get("mainsnak", {})
            if mainsnak.get("snaktype") == "value":
                iso_codes.append(mainsnak["datavalue"].get("value", "").lower())

    if not iso_codes:
        print(f"Warning: No ISO 3166-2 code found for '{name}' ({qid})")
        return

    iso_code_wikidata = iso_codes[1] if len(iso_codes) > 1 else iso_codes[0]
    iso_code_wikidata = iso_code_wikidata.lower().replace("-", "_")
    # Compare ISO codes
    if iso_code_wikidata != code:
        print(
            f"Warning: Mismatch between provided code '{code}' and Wikidata code '{iso_code_wikidata}'"
        )
        return

    with open(path, "w") as wfh:
        yaml.dump(data, wfh, indent=2, allow_unicode=True, sort_keys=True)


if __name__ == "__main__":
    fetch_territory(sys.argv[1], sys.argv[2])
