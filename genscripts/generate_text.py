from genscripts.util import RESOURCES_PATH


TEMPLATE = """
from typing import List
"""


def generate_scripts_ranges() -> None:
    """Generate the scripts ranges file."""
    scripts_path = RESOURCES_PATH / "text" / "scripts.txt"

    with open(scripts_path, "r", encoding="utf-8") as fh:
        while line := fh.readline():
            line = line.split("#")[0].strip()
            if not line:
                continue
            parts = line.split(";")
            range = parts[0].strip()
            if ".." in range:
                range = range.split("..")
                start = int(range[0], 16)
                end = int(range[1], 16)
            else:
                start = int(range, 16)
                end = start
            script = parts[1].strip()
            print(script, start, end)


if __name__ == "__main__":
    generate_scripts_ranges()
