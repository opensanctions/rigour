from datetime import datetime, timezone, date
from rigour.time import utc_now, naive_now, utc_date


def test_utc_now():
    assert utc_now() is not None
    assert isinstance(utc_now(), datetime)
    assert utc_now().tzinfo == timezone.utc
    assert utc_date() is not None
    assert isinstance(utc_date(), date)
    assert utc_date() == utc_now().date()


def test_naive_now():
    assert naive_now() is not None
    assert isinstance(naive_now(), datetime)
    assert naive_now().tzinfo is None
    assert naive_now().date() == utc_now().date()
    assert naive_now().day == utc_now().day
