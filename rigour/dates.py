"""Compare imprecise FtM dates without pretending they are exact instants.

An FtM date is a prefix such as ``2026`` or ``2026-06``. Each prefix describes
an interval, not the first instant in that interval: ``2026`` could mean any
time during that year. The public helpers below deliberately answer questions
about the interval's start or end so callers do not accidentally fall back to
lexicographic string comparisons.
"""

import re
from datetime import datetime, timedelta
from functools import lru_cache

from prefixdate import Precision, parse

from rigour.util import MEMO_SMALL

# ``prefixdate`` intentionally accepts messy source data and may parse only the
# valid prefix of a string. These helpers operate on normalized FtM values, so
# first require the whole input to have a canonical prefix-date shape. Calendar
# validation and precision detection are still delegated to ``prefixdate``.
_PREFIX_RE = re.compile(
    r"^[12]\d{3}"
    r"(?:-\d{2}"
    r"(?:-\d{2}"
    r"(?:T\d{2}"
    r"(?::\d{2}"
    r"(?::\d{2})?"
    r")?"
    r")?"
    r")?"
    r")?$"
)
# A reference is a point in time rather than another imprecise interval. Require
# seconds so comparisons against a day or month cannot acquire hidden semantics.
_REFERENCE_RE = re.compile(r"^[12]\d{3}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$")
_OFFSET_RE = re.compile(r"(?P<sign>[+-])(?P<hour>\d{2})(?::?(?P<minute>\d{2}))?$")


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _without_timezone(value: str) -> tuple[str, bool]:
    """Remove an explicit UTC suffix while rejecting offsets needing conversion."""
    if value.endswith("Z"):
        return value[:-1], True
    if "T" not in value:
        return value, False
    match = _OFFSET_RE.search(value)
    if match is None:
        return value, False
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    # FtM timestamps are either naive UTC or explicitly UTC. Converting another
    # offset here could hide an upstream violation of that data contract.
    if hour != 0 or minute != 0:
        raise ValueError("date timestamps must be naive or UTC")
    return value[: match.start()], True


@lru_cache(maxsize=MEMO_SMALL)
def _date_bounds(value: str) -> tuple[datetime, datetime]:
    """Expand a prefix date into a half-open ``[start, end)`` interval."""
    text, had_timezone = _without_timezone(value)
    if _PREFIX_RE.fullmatch(text) is None:
        raise ValueError(f"Invalid prefix date: {value!r}")

    # The shape check above prevents partial parses. ``prefixdate`` remains the
    # source of truth for real dates (including leap years) and their precision.
    prefix = parse(text)
    if prefix.dt is None or prefix.text is None or prefix.precision == Precision.EMPTY:
        raise ValueError(f"Invalid prefix date: {value!r}")
    if prefix.text != text:
        raise ValueError(f"Prefix date is not canonical: {value!r}")
    if had_timezone and prefix.precision != Precision.SECOND:
        raise ValueError("timezone suffixes require second precision")

    start = prefix.dt.replace(tzinfo=None)
    precision = prefix.precision
    # Advancing by one unit gives an exclusive end without inventing an
    # artificial "latest" microsecond. It also makes boundaries exact: a day
    # used as an end date expires at midnight at the start of the next day.
    if precision == Precision.YEAR:
        end = start.replace(year=start.year + 1)
    elif precision == Precision.MONTH:
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    elif precision == Precision.DAY:
        end = start + timedelta(days=1)
    elif precision == Precision.HOUR:
        end = start + timedelta(hours=1)
    elif precision == Precision.MINUTE:
        end = start + timedelta(minutes=1)
    elif precision == Precision.SECOND:
        end = start + timedelta(seconds=1)
    else:
        raise ValueError(f"Unsupported prefix date precision: {value!r}")
    return start, end


@lru_cache(maxsize=MEMO_SMALL)
def _reference_datetime(value: str) -> datetime:
    """Parse the exact point against which a prefix interval is compared."""
    text, _ = _without_timezone(value)
    if _REFERENCE_RE.fullmatch(text) is None:
        raise ValueError(f"Invalid reference timestamp: {value!r}")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"Invalid reference timestamp: {value!r}") from exc


def ended_before(value: str, reference: str) -> bool:
    """Check whether a prefix date has completely elapsed before a timestamp.

    Use this for end dates and age cutoffs where an imprecise date should remain
    current until its latest possible instant has passed.

    Args:
        value: Canonical FtM prefix date, from year through second precision.
        reference: Exact naive or UTC ISO timestamp, including seconds.

    Returns:
        True if every instant represented by ``value`` precedes ``reference``.

    Raises:
        TypeError: If either argument is not a string.
        ValueError: If either argument is invalid or uses a non-UTC offset.
    """
    value = _require_string(value, "value")
    reference = _require_string(reference, "reference")
    _, end = _date_bounds(value)
    # With an exclusive end, equality means the whole represented interval has
    # elapsed: 2026 ends exactly at 2027-01-01T00:00:00.
    return end <= _reference_datetime(reference)


def starts_after(value: str, reference: str) -> bool:
    """Check whether a prefix date begins after a timestamp.

    Use this for start dates and future-date guardrails where even the earliest
    possible instant must be later than the reference.

    Args:
        value: Canonical FtM prefix date, from year through second precision.
        reference: Exact naive or UTC ISO timestamp, including seconds.

    Returns:
        True if every instant represented by ``value`` follows ``reference``.

    Raises:
        TypeError: If either argument is not a string.
        ValueError: If either argument is invalid or uses a non-UTC offset.
    """
    value = _require_string(value, "value")
    reference = _require_string(reference, "reference")
    start, _ = _date_bounds(value)
    # Strict comparison keeps a date beginning exactly at the reference from
    # being labelled as starting after it.
    return start > _reference_datetime(reference)
