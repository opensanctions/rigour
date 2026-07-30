from collections.abc import Iterable, Mapping
from typing import Any

ParamsType = Iterable[tuple[str, Any]] | Mapping[str, Any] | None

SCHEMES = ("http", "https", "ftp", "mailto", "file", "s3", "gs")
DEFAULT_SCHEME = "http"
