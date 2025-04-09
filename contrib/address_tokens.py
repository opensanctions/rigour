import sys
import csv
from collections import Counter

from rigour.addresses import normalize_address


def parse_addresses(file_path):
    tokens = Counter()
    with open(file_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        count = 0
        for row in reader:
            if row["prop_type"] != "address":
                continue
            count += 1
            if count % 10000 == 0:
                print(count)
            # if count > 500000:
            #     break
            value = row["value"]
            normalized = normalize_address(value)
            if normalized is None:
                continue
            for token in normalized.split(" "):
                token = token.strip()
                if len(token) < 2:
                    continue
                try:
                    int(token)
                    continue
                except ValueError:
                    pass
                tokens[token] += 1
    print("Tokens:")
    for token, count in tokens.most_common(500):
        print(f"{token}: {count}")


if __name__ == "__main__":
    statements_path = sys.argv[1]
    parse_addresses(statements_path)
