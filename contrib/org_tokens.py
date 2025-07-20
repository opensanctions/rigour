import sys
import csv
from collections import Counter
from typing import Callable

from rigour.names import normalize_name
from rigour.names.org_types import remove_org_types
from rigour.text.dictionary import Scanner
from rigour.data.names import data


def org_name_processor() -> Callable[[str], str]:
    forms = set()
    for key, values in data.ORG_SYMBOLS.items():
        forms.add(normalize_name(key))
        for value in values:
            forms.add(normalize_name(value))
    for stopword in data.STOPWORDS:
        forms.add(normalize_name(stopword))
    for phrase in data.STOPPHRASES:
        forms.add(normalize_name(phrase))
    flist = [f for f in forms if f is not None]
    scanner = Scanner(flist, ignore_case=True)

    def processor(text: str) -> str:
        return scanner.remove(text)

    return processor


def parse_names(file_path):
    tokens = Counter()
    processor = org_name_processor()
    with open(file_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        count = 0
        for row in reader:
            if row["schema"] not in ("Organization", "Company"):
                continue
            if row["prop_type"] != "name":
                continue
            # dataset = row["dataset"]
            # if dataset not in (
            #     "eu_fsf",
            #     # "ext_ru_egrul",
            #     # "ua_nsdc_sanctions",
            #     "us_ofac_sdn",
            #     "us_ofac_cons",
            #     "ch_seco_sanctions",
            #     "gb_hmt_sanctions",
            #     "gb_fcdo_sanctions",
            #     "us_sam_exclusions",
            #     "be_fod_sanctions",
            # ):
            #     continue
            count += 1
            if count % 10000 == 0:
                print(count)
            # if count > 500000:
            #     break
            value = normalize_name(row["value"])
            if value is None:
                continue
            value = remove_org_types(value, normalizer=normalize_name)
            value = processor(value)
            for token in value.split(" "):
                if len(token) < 2:
                    continue
                try:
                    int(token)
                    continue
                except ValueError:
                    pass
                tokens[token] += 1

    print("Tokens:")
    for token, count in tokens.most_common(2000):
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
