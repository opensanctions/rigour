from datetime import datetime, date, timezone


def utc_now() -> datetime:
    """Return the current datetime in UTC."""
    return datetime.now(timezone.utc)


def utc_date() -> date:
    """Return the current date in UTC."""
    return utc_now().date()
