"""Compare prefix dates without pretending they are exact instants.

A prefix date such as ``2026`` or ``2026-06`` represents an interval, rather
than the first instant of that year or month. Use the string wrappers for
one-off comparisons, or parse a [DateInterval][rigour.dates.DateInterval] once
when comparing the same value repeatedly.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from prefixdate import Precision, parse

from rigour.util import MEMO_SMALL

_TIMEZONE_SUFFIX_RE = re.compile(r"(?:Z|[+-]\d{2}(?::?\d{2})?)$")
_SECOND_TIMESTAMP_RE = re.compile(
    r"^[12]\d{3}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:Z|[+-]\d{2}(?::?\d{2})?)?$"
)


@dataclass(frozen=True)
class DateInterval:
    """Represent every possible instant described by an imprecise date.

    Use this parsed form when applying multiple comparisons to the same prefix
    date. Both bounds are timezone-aware UTC datetimes and ``end`` is exclusive.

    Attributes:
        start: Earliest instant represented by the date.
        end: First instant after the represented interval.
    """

    start: datetime
    end: datetime


def _ensure_utc(value: datetime) -> datetime:
    """Adapt legacy naive-UTC values to aware UTC datetimes."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def require_utc(value: str) -> datetime:
    """Parse an exact timestamp as an aware UTC datetime.

    Use this at a prefix-date boundary where an exact timestamp may carry an
    offset. Naive timestamps use the ecosystem convention of implicit UTC.

    Args:
        value: Canonical second-precision timestamp.

    Returns:
        The represented instant as a timezone-aware UTC datetime.

    Raises:
        ValueError: The timestamp is invalid or is not precise to the second.
    """
    if _SECOND_TIMESTAMP_RE.fullmatch(value) is None:
        raise ValueError(f"Invalid exact timestamp: {value!r}")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp: {value!r}") from exc
    return _ensure_utc(timestamp)


@lru_cache(maxsize=MEMO_SMALL)
def prefix_interval(value: str) -> DateInterval:
    """Expand a canonical prefix date into its represented UTC interval.

    Use this at the boundary between prefix-date strings and interval comparison.
    Exact timestamps with offsets are converted to UTC before their one-second
    interval is constructed.

    Args:
        value: Canonical prefix date, from year through second precision.

    Returns:
        The timezone-aware UTC, half-open interval represented by the value.

    Raises:
        ValueError: The value is invalid or non-canonical, or an imprecise value
            carries a timezone.
    """
    if _SECOND_TIMESTAMP_RE.fullmatch(value) is not None:
        start = require_utc(value)
        return DateInterval(start=start, end=start + timedelta(seconds=1))
    has_timezone = value.endswith("Z") or (
        "T" in value and _TIMEZONE_SUFFIX_RE.search(value) is not None
    )
    if has_timezone:
        raise ValueError("timezone suffixes require second precision")

    prefix = parse(value)
    if prefix.dt is None or prefix.text is None or prefix.precision == Precision.EMPTY:
        raise ValueError(f"Invalid prefix date: {value!r}")
    if prefix.text != value:
        raise ValueError(f"Prefix date is not canonical: {value!r}")

    start = prefix.dt.replace(tzinfo=timezone.utc)
    precision = prefix.precision
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
    return DateInterval(start=start, end=end)


def interval_ended_before(value: DateInterval, reference: datetime) -> bool:
    """Check whether an interval has completely elapsed before a point in time.

    Use this for end dates and age cutoffs when the prefix date has already been
    parsed.

    Args:
        value: Interval to compare.
        reference: Timezone-aware UTC point in time.

    Returns:
        ``True`` if every instant represented by the interval precedes the
        reference.
    """
    return value.end <= reference


def interval_starts_after(value: DateInterval, reference: datetime) -> bool:
    """Check whether an interval begins strictly after a point in time.

    Use this for start dates and future-date guardrails when the prefix date has
    already been parsed.

    Args:
        value: Interval to compare.
        reference: Timezone-aware UTC point in time.

    Returns:
        ``True`` if the earliest instant in the interval follows the reference.
    """
    return value.start > reference


def ended_before(value: str, reference: datetime) -> bool:
    """Check whether a prefix date has completely elapsed.

    Use this string wrapper for one-off end-date and age-cutoff checks. Parse
    once with [prefix_interval][rigour.dates.prefix_interval] when making
    several comparisons against the same value.

    Args:
        value: Canonical prefix date, from year through second precision.
        reference: UTC point in time. Legacy naive values are interpreted as
            UTC; aware values are converted to UTC.

    Returns:
        ``True`` if every instant represented by the date precedes the
        reference.
    """
    return interval_ended_before(prefix_interval(value), _ensure_utc(reference))


def starts_after(value: str, reference: datetime) -> bool:
    """Check whether a prefix date begins after a point in time.

    Use this string wrapper for one-off start-date and future-date checks. Parse
    once with [prefix_interval][rigour.dates.prefix_interval] when reusing the
    same value.

    Args:
        value: Canonical prefix date, from year through second precision.
        reference: UTC point in time. Legacy naive values are interpreted as
            UTC; aware values are converted to UTC.

    Returns:
        ``True`` if the earliest instant represented by the date follows the
        reference.
    """
    return interval_starts_after(prefix_interval(value), _ensure_utc(reference))
