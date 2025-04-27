import sys
import csv
from collections import Counter

from rigour.names import tokenize_name
from rigour.names.org_types import replace_org_types_display, normalize_display


def parse_names(file_path):
    tokens = Counter()
    with open(file_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        count = 0
        for row in reader:
            if row["schema"] not in ("Organization", "Company"):
                continue
            if row["prop_type"] != "name":
                continue
            dataset = row["dataset"]
            if dataset.startswith("ru_"):
                continue
            count += 1
            if count % 10000 == 0:
                print(count)
            # if count > 500000:
            #     break
            value = normalize_display(row["value"])
            value = replace_org_types_display(value)
            for token in tokenize_name(value.lower()):
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


if __name__ == "__main__":
    statements_path = sys.argv[1]
    parse_names(statements_path)
