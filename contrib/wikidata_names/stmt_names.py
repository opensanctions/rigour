import sys
import csv
from pathlib import Path
from collections import Counter
from typing import Dict

from rigour.names import tokenize_name


def read_mapping() -> Dict[str, str]:
    path = Path("out/wd_names_strict.txt")
    mapping: Dict[str, str] = {}
    with open(path, "r") as fh:
        while line := fh.readline():
            aliases_, target = line.split(" => ", 1)
            target = target.strip()
            mapping[target] = target
            aliases = aliases_.split(", ")
            for alias in aliases:
                mapping[alias] = target
    return mapping


def parse_person_names(file_path):
    tokens = Counter()
    mapping = read_mapping()
    with open(file_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        count = 0
        for row in reader:
            if row["schema"] != "Person":
                continue
            if row["prop_type"] != "name":
                continue
            count += 1
            if count % 10000 == 0:
                print(count)
            # if count > 500000:
            #     break
            value = row["value"]
            for token in tokenize_name(value.lower()):
                token = token.strip()
                if len(token) < 2:
                    continue
                if token in mapping:
                    continue
                tokens[token] += 1
    print("Tokens:")
    for token, count in tokens.most_common(500):
        print(f"{token}: {count}")


if __name__ == "__main__":
    statements_path = sys.argv[1]
    parse_person_names(statements_path)
