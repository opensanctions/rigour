import warnings
from datetime import date, datetime, timezone
from functools import lru_cache

from rigour.util import MEMO_SMALL


def utc_now() -> datetime:
    """Return the current datetime in UTC."""
    return datetime.now(timezone.utc)


def naive_now() -> datetime:
    """Return the current datetime as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_date() -> date:
    """Return the current date in UTC."""
    return utc_now().date()


@lru_cache(maxsize=MEMO_SMALL)
def iso_datetime(value: str | None) -> datetime | None:
    """Parse a timestamp in the FollowTheMoney wire format into an aware UTC datetime.

    This is the inverse of [datetime_iso][rigour.time.datetime_iso]: it reads
    `'YYYY-MM-DDTHH:MM:SS'` and ignores anything after the seconds, so it also
    accepts the fractional-second and offset-bearing forms that older writers in
    the ecosystem emitted. It is not a general ISO 8601 parser.

    Args:
        value: The timestamp to parse, or None.

    Returns:
        An aware datetime in UTC, or None if the input was None or empty.

    Raises:
        ValueError: If the leading 19 characters are not a date and time.
    """
    if value is None or len(value) == 0:
        return None
    value = value[:19].replace(" ", "T")
    # The format has no offset, and any offset on the input is discarded above:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def datetime_iso(dt: datetime) -> str | None:
    """Format a datetime as a timestamp in the FollowTheMoney wire format.

    Use this at every point where a timestamp is serialized for publication, so
    that the same field never ships in two different shapes. The output is
    `'YYYY-MM-DDTHH:MM:SS'` in UTC with no offset suffix, which
    [iso_datetime][rigour.time.iso_datetime] reads back exactly.

    Naive datetimes are taken to be UTC already, matching the convention of
    [naive_now][rigour.time.naive_now]. An aware datetime in another zone is
    converted to UTC before truncation - dropping the offset without converting
    would shift the timestamp - and a warning is emitted, since carrying local
    time this far usually means the value was built without a timezone in mind.

    Args:
        dt: The datetime to serialize, or None.

    Returns:
        The formatted timestamp, or None if the input was None.
    """
    if dt is None:
        return dt
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elif dt.tzinfo != timezone.utc:
            warnings.warn(
                f"datetime_iso expects UTC timezone, but got {dt.tzinfo}. "
                "Consider using utc_now() or converting to UTC first.",
                UserWarning,
                stacklevel=2,
            )
            dt = dt.astimezone(timezone.utc)

        return dt.replace(tzinfo=None).isoformat(sep="T", timespec="seconds")
    except AttributeError:
        if isinstance(dt, str):
            warnings.warn(
                "datetime_iso received a string, supports only datetime objects.",
                UserWarning,
                stacklevel=2,
            )
        outvalue = str(dt)
        return outvalue.replace(" ", "T")[:19]
