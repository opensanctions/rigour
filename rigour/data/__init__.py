import orjson
from pathlib import Path
from typing import Any, Generator


DATA_PATH = Path(__file__).resolve().parent


def read_jsonl(file_name: str) -> Generator[Any, None, None]:
    """Read a JSONL file and yield each line as a dictionary."""
    file_path = DATA_PATH / file_name
    with open(file_path, "rb") as fh:
        for line in fh:
            yield orjson.loads(line)
