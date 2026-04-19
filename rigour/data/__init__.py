import orjson
from pathlib import Path
from typing import Any, Generator


DATA_PATH = Path(__file__).resolve().parent


def iter_jsonl_text(text: str) -> Generator[Any, None, None]:
    """Parse newline-delimited JSON from a string.

    Used by the territories and future tagger paths to parse JSONL
    returned from the Rust crate (`rigour._core.territories_jsonl()`
    etc.) without going through the filesystem. Empty / whitespace-
    only lines are skipped.
    """
    for line in text.splitlines():
        if line.strip():
            yield orjson.loads(line)
