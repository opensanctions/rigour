from functools import lru_cache
import sys
import csv
from collections import Counter
from normality.cleaning import compose_nfc

from rigour.names import tokenize_name
from rigour.names.org_types import remove_org_types, normalize_display
from rigour.data.names import data


@lru_cache(maxsize=20000)
def normalize(name: str) -> str:
    """Normalize the name by removing special characters and converting to lowercase."""
    # Remove special characters and convert to lowercase
    name = compose_nfc(name).lower()
    name = " ".join(tokenize_name(name.lower()))
    return name


def ignore_list():
    """Return a set of ignored tokens."""
    ignored = set()
    for sw in data.STOPWORDS:
        ignored.add(normalize(sw))
    for key, values in data.ORG_SYMBOLS.items():
        ignored.add(normalize(key))
        for value in values:
            ignored.add(normalize(value))
    return ignored


def parse_names(file_path):
    tokens = Counter()
    ignored = ignore_list()
    with open(file_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        count = 0
        for row in reader:
            if row["schema"] not in ("Organization", "Company"):
                continue
            if row["prop_type"] != "name":
                continue
            dataset = row["dataset"]
            if dataset not in (
                "eu_fsf",
                "ext_ru_egrul",
                "ua_nsdc_sanctions",
                "us_ofac_sdn",
                "us_ofac_cons",
                "ch_seco_sanctions",
                "gb_hmt_sanctions",
                "gb_fcdo_sanctions",
                "us_sam_exclusions",
                "be_fod_sanctions",
            ):
                continue
            count += 1
            if count % 10000 == 0:
                print(count)
            # if count > 500000:
            #     break
            value = normalize_display(row["value"])
            if value is None:
                continue
            value = remove_org_types(value)
            for token in tokenize_name(value.lower()):
                if len(token) < 2 or token in ignored:
                    continue
                try:
                    int(token)
                    continue
                except ValueError:
                    pass
                tokens[token] += 1

    print("Tokens:")
    for token, count in tokens.most_common(1000):
        print(f"{token}: {count}")

    # print("Similar to existing symbols:")
    # for token, _ in tokens.most_common(100000):
    #     if not is_modern_alphabet(token):
    #         continue
    #     for _, values in data.ORG_SYMBOLS.items():
    #         for val in values:
    #             nvalue = normalize(val)
    #             # if nvalue in ignored:
    #             #     continue
    #             if not is_modern_alphabet(nvalue):
    #                 continue
    #             if len(nvalue) < 8:
    #                 continue
    #             # if len(nvalue) < 3 or nvalue == token:
    #             #     continue
    #             # print(nvalue, token)
    #             if levenshtein(nvalue, token) < 4:
    #                 print(f"{token}: {val}")
    #                 # break
    #             # print(f"{token}: {count} ({k})")
    #             # break
    #         #


if __name__ == "__main__":
    statements_path = sys.argv[1]
    parse_names(statements_path)
