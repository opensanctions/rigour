from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from urllib.parse import ParseResult
from collections.abc import Mapping

from rigour.urls.util import ParamsType, DEFAULT_SCHEME, SCHEMES


def build_url(url: str, params: ParamsType = None) -> str:
    """Compose a URL with the given query parameters."""
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if params is not None:
        values = params.items() if isinstance(params, Mapping) else params
        query.extend(sorted(values))
    parsed = parsed._replace(query=urlencode(query))
    return urlunparse(parsed)


def _clean_url(text: str) -> Optional[ParseResult]:
    """Perform intensive care on URLs to make sure they have a scheme
    and a host name. If no scheme is given HTTP is assumed."""
    try:
        parsed = urlparse(text)
    except (TypeError, ValueError):  # pragma: no cover
        return None
    if not len(parsed.netloc):
        if "." in parsed.path and not text.startswith("//"):
            # This is a pretty weird rule meant to catch things like
            # 'www.google.com', but it'll likely backfire in some
            # really creative ways.
            return _clean_url(f"//{text}")
        return None
    if not len(parsed.scheme):
        parsed = parsed._replace(scheme=DEFAULT_SCHEME)
    else:
        parsed = parsed._replace(scheme=parsed.scheme.lower())
    if parsed.scheme not in SCHEMES:
        return None
    parsed = parsed._replace(path=parsed.path.strip())
    if not len(parsed.path):
        parsed = parsed._replace(path="/")
    return parsed


def clean_url(text: str) -> Optional[str]:
    """Perform intensive care on URLs to make sure they have a scheme
    and a host name. If no scheme is given HTTP is assumed."""
    parsed = _clean_url(text)
    if parsed is None:
        return None
    return parsed.geturl()


def clean_url_compare(text: str) -> Optional[str]:
    """Destructively clean a URL for comparison."""
    parsed = _clean_url(text)
    if parsed is None:
        return None
    if parsed.scheme == "https":
        parsed = parsed._replace(scheme="http")
    hostname = parsed.netloc.lower()
    hostname = hostname.replace("www.", "")
    parsed = parsed._replace(netloc=hostname)
    parsed = parsed._replace(fragment="")
    query = parse_qsl(parsed.query, keep_blank_values=False)
    parsed = parsed._replace(query=urlencode(sorted(query)))
    return parsed.geturl()
