import requests

from rigour.territories import get_territory, get_ftm_countries

res = requests.get(
    "https://opensanctions.directus.app/items/territories?limit=5000"
).json()

FTM_CODES = [t.code for t in get_ftm_countries()]
SEEN_CODES = []

for terr in res["data"]:
    tcode = terr["code"]
    if tcode not in FTM_CODES:
        print("Exists in CMS but not in FTM:", tcode, terr["label_short"])
    tobj = get_territory(tcode)
    if not tobj:
        print("Exists in CMS but not in FTM:", tcode, terr["label_short"])
    SEEN_CODES.append(tcode)

FTM_MISSING = [c for c in FTM_CODES if c not in SEEN_CODES]
print("Missing in CMS:", FTM_MISSING)
