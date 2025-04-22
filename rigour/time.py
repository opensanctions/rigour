from datetime import datetime, date, timezone
from functools import lru_cache
from typing import Optional, Union


def utc_now() -> datetime:
    """Return the current datetime in UTC."""
    return datetime.now(timezone.utc)


def naive_now() -> datetime:
    """Return the current datetime as a naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_date() -> date:
    """Return the current date in UTC."""
    return utc_now().date()


@lru_cache(maxsize=1000)
def iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse datetime from standardized date string. This expects an ISO 8601 formatted
    string, e.g. '2023-10-01T12:00:00'. Any additional characters after the seconds will
    be ignored. The string is converted to a datetime object with UTC timezone. This is
    not designed to parse all possible ISO 8601 formats, but rather a specific convention
    used in the context of the FollowTheMoney ecosystem."""
    if value is None or len(value) == 0:
        return None
    value = value[:19].replace(" ", "T")
    dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def datetime_iso(dt: Optional[Union[str, datetime]]) -> Optional[str]:
    """Convert a datetime object or string to an ISO 8601 formatted string. If the input
    is None, it returns None. If the input is a string, it is returned as is. Otherwise,
    the datetime object is converted to a string in the format 'YYYY-MM-DDTHH:MM:SS'."""
    if dt is None:
        return dt
    try:
        return dt.isoformat(sep="T", timespec="seconds")  # type: ignore
    except AttributeError:
        outvalue = str(dt)
        return outvalue.replace(" ", "T")
