from typing import Any, Iterable, Mapping, Tuple, Union

ParamsType = Union[None, Iterable[Tuple[str, Any]], Mapping[str, Any]]

SCHEMES = ("http", "https", "ftp", "mailto", "file", "s3", "gs")
DEFAULT_SCHEME = "http"
