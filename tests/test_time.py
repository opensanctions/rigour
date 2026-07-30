from datetime import date, datetime, timedelta, timezone

import pytest

from rigour.time import datetime_iso, iso_datetime, naive_now, utc_date, utc_now


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

    # Offsets are ignored on input, as they were never in the wire format:
    offset = iso_datetime("2023-10-01T12:00:00+05:30")
    assert offset == example


def test_datetime_iso():
    example = datetime(2023, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert datetime_iso(example) == "2023-10-01T12:00:00"

    # Naive datetimes are UTC by convention, not local time:
    assert datetime_iso(example.replace(tzinfo=None)) == "2023-10-01T12:00:00"

    # Microseconds are dropped, so the output round-trips:
    assert datetime_iso(example.replace(microsecond=123456)) == "2023-10-01T12:00:00"

    # A foreign timezone is converted, not just stripped:
    other = datetime(
        2023, 10, 1, 17, 30, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )
    with pytest.warns(UserWarning):
        assert datetime_iso(other) == "2023-10-01T12:00:00"

    with pytest.warns(UserWarning):
        assert datetime_iso("2023-10-01 12:00:00") == "2023-10-01T12:00:00"

    with pytest.warns(UserWarning):
        assert datetime_iso("2023-10-01T12:00:00+00:00") == "2023-10-01T12:00:00"

    assert datetime_iso(None) is None


def test_datetime_iso_roundtrip():
    for text in (
        "2023-10-01T12:00:00",
        "2023-10-01T00:00:00",
        "2026-07-29T08:54:49",
    ):
        assert datetime_iso(iso_datetime(text)) == text

    now = utc_now()
    assert iso_datetime(datetime_iso(now)) == now.replace(microsecond=0)
