import re
import time
from pathlib import Path
from typing import Dict


def compile_mapping(mapping: Dict[str, str]) -> re.Pattern[str]:
    forms = [re.escape(n) for n in mapping.keys()]
    forms = sorted(forms, key=len, reverse=True)
    print(forms[:1000])
    joined = "|".join(forms)
    return re.compile(f"\\b({joined})\\b", re.IGNORECASE | re.UNICODE)


def read_mapping(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with open(path, "r") as fh:
        while line := fh.readline():
            aliases_, target = line.split(" => ", 1)
            target = target.strip()
            aliases = aliases_.split(", ")
            for alias in aliases:
                mapping[alias] = target
    return mapping


if __name__ == "__main__":
    data_path = Path("out/wd_names_strict.txt")
    mapping = read_mapping(data_path)
    pattern = compile_mapping(mapping)
    print("compiled", len(mapping), pattern)

    def subby(match: re.Match[str]):
        value = match.group(0).lower()
        return mapping[value]

    print("XXX", pattern.subn(subby, "Владимир Путин"))
    time.sleep(60)
