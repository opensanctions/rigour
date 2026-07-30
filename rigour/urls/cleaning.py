import re
from collections.abc import Mapping
from ipaddress import ip_address
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse

from rigour.urls.util import DEFAULT_SCHEME, SCHEMES, ParamsType

# A single host label, capped at the DNS length limit. `\w` matches letters in
# any script, so a domain is accepted both in its decoded IDN form (`пример.рф`)
# and as punycode (`xn--e1afmkfd.xn--p1ai`).
HOST_LABEL = re.compile(r"[\w-]{1,63}", re.UNICODE)
# A letter or digit in any script, i.e. a label that is not just punctuation.
HOST_ALNUM = re.compile(r"[^\W_]", re.UNICODE)
WHITESPACE = re.compile(r"\s")


def build_url(url: str, params: ParamsType = None) -> str:
    """Compose a URL with the given query parameters."""
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if params is not None:
        values = params.items() if isinstance(params, Mapping) else params
        query.extend(sorted(values))
    parsed = parsed._replace(query=urlencode(query))
    return urlunparse(parsed)


def _is_valid_netloc(parsed: ParseResult) -> bool:
    """Check that the authority of a parsed URL is a plausible host name.

    `urlparse` accepts everything up to the first slash as the authority, so it
    never rejects free text: a label someone typed into a spreadsheet's website
    column ("Social media: http://vk.com/x") parses as a URL whose host is that
    prose. Screening the host is what keeps such values from being emitted as
    URLs that merely look well-formed.
    """
    if WHITESPACE.search(parsed.netloc) is not None:
        return False
    try:
        host = parsed.hostname
        _ = parsed.port  # raises for a non-numeric or out-of-range port
    except ValueError:
        return False
    if host is None or len(host) == 0:
        return False
    try:
        ip_address(host)
        return True
    except ValueError:
        pass
    labels = host.rstrip(".").split(".")
    for label in labels:
        if HOST_LABEL.fullmatch(label) is None:
            return False
        if HOST_ALNUM.search(label) is None:
            return False
    # No public suffix is a single character or all digits, so this rejects
    # decimals and abbreviations read as host names ("3.4", "N.A.").
    if len(labels) > 1 and (len(labels[-1]) < 2 or labels[-1].isdigit()):
        return False
    return True


def _clean_url(text: str) -> ParseResult | None:
    """Perform intensive care on URLs to make sure they have a scheme
    and a host name. If no scheme is given HTTP is assumed."""
    try:
        parsed = urlparse(text)
    except (TypeError, ValueError):  # pragma: no cover
        return None
    if not len(parsed.netloc):
        # A supported scheme with no authority is a URL this function cannot
        # handle (`mailto:`, `file:`) or a mangled one (`https:example.com`).
        # Bail out before the rule below invents a host name from the path.
        if parsed.scheme.lower() in SCHEMES:
            return None
        if "." in parsed.path and not text.startswith("//"):
            # This is a pretty weird rule meant to catch things like
            # 'www.google.com', but it'll likely backfire in some
            # really creative ways.
            return _clean_url(f"//{text}")
        return None
    if not _is_valid_netloc(parsed):
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


def clean_url(text: str) -> str | None:
    """Perform intensive care on URLs to make sure they have a scheme
    and a host name. If no scheme is given HTTP is assumed."""
    parsed = _clean_url(text)
    if parsed is None:
        return None
    return parsed.geturl()


def clean_url_compare(text: str) -> str | None:
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
