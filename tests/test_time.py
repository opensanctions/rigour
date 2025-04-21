import pytest
from datetime import datetime, timezone, date
from rigour.time import utc_now, naive_now, utc_date
from rigour.time import iso_datetime, datetime_iso


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


def test_iso_datetime():
    assert iso_datetime("") is None
    assert iso_datetime(None) is None
    example = iso_datetime("2023-10-01T12:00:00")
    assert example is not None
    assert isinstance(example, datetime)
    assert example.tzinfo == timezone.utc
    assert example.year == 2023
    assert example.month == 10
    assert example.day == 1
    assert example.hour == 12
    assert example.minute == 0
    assert example.second == 0

    other = iso_datetime("2023-10-01 12:00:00.123456")
    assert other is not None
    assert other == example

    with pytest.raises(ValueError):
        iso_datetime("2023-10-01")

    with pytest.raises(ValueError):
        iso_datetime("2023-10-01 12:00:")

    assert datetime_iso(None) is None
    assert datetime_iso("2023-10-01T12:00:00") == "2023-10-01T12:00:00"
    assert datetime_iso("2023-10-01 12:00:00") == "2023-10-01T12:00:00"
    assert datetime_iso(example) == "2023-10-01T12:00:00+00:00"
