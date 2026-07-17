from datetime import datetime, timedelta, timezone

import pytest

from rigour.dates import (
    DateInterval,
    ended_before,
    interval_ended_before,
    interval_starts_after,
    parse_utc,
    prefix_interval,
    starts_after,
)


def dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def test_ended_before_prefix_precision() -> None:
    assert not ended_before("2026", dt("2026-07-17T12:00:00"))
    assert ended_before("2026", dt("2027-01-01T00:00:00"))

    assert not ended_before("2026-06", dt("2026-06-30T23:59:59"))
    assert ended_before("2026-06", dt("2026-07-01T00:00:00"))

    assert not ended_before("2026-06-15", dt("2026-06-15T23:59:59"))
    assert ended_before("2026-06-15", dt("2026-06-16T00:00:00"))

    assert not ended_before("2026-06-15T12", dt("2026-06-15T12:59:59"))
    assert ended_before("2026-06-15T12", dt("2026-06-15T13:00:00"))

    assert not ended_before("2026-06-15T12:30", dt("2026-06-15T12:30:59"))
    assert ended_before("2026-06-15T12:30", dt("2026-06-15T12:31:00"))

    assert not ended_before(
        "2026-06-15T12:30:45", dt("2026-06-15T12:30:45.500000")
    )
    assert ended_before("2026-06-15T12:30:45", dt("2026-06-15T12:30:46"))


def test_starts_after_boundaries() -> None:
    assert starts_after("2027", dt("2026-12-31T23:59:59"))
    assert not starts_after("2027", dt("2027-01-01T00:00:00"))
    assert starts_after("2068-07-16", dt("2026-07-17T12:00:00"))
    assert not starts_after("2026", dt("2026-07-17T12:00:00"))


def test_calendar_boundaries() -> None:
    assert ended_before("2024-02", dt("2024-03-01T00:00:00"))
    assert ended_before("2024-02-29", dt("2024-03-01T00:00:00"))
    assert ended_before("2026-12", dt("2027-01-01T00:00:00"))


def test_prefix_interval_uses_aware_utc_bounds() -> None:
    interval = prefix_interval("2026-06")
    assert interval == DateInterval(
        start=dt("2026-06-01T00:00:00+00:00"),
        end=dt("2026-07-01T00:00:00+00:00"),
    )


def test_interval_and_string_predicates_are_equivalent() -> None:
    interval = prefix_interval("2026")
    reference = dt("2027-01-01T00:00:00")
    assert interval_ended_before(interval, reference) == ended_before("2026", reference)
    assert interval_starts_after(interval, reference) == starts_after("2026", reference)


def test_string_wrapper_accepts_legacy_naive_utc_reference() -> None:
    interval = prefix_interval("2026")
    reference = datetime(2027, 1, 1)
    assert ended_before("2026", reference)
    with pytest.raises(TypeError, match="offset-naive and offset-aware"):
        interval_ended_before(interval, reference)


def test_string_wrapper_converts_aware_reference_to_utc() -> None:
    assert ended_before("2026", dt("2027-01-01T01:00:00+01:00"))


@pytest.mark.parametrize("suffix", ["Z", "+00", "+0000", "+00:00"])
def test_utc_suffixes(suffix: str) -> None:
    value = f"2026-12-31T23:59:59{suffix}"
    assert parse_utc(value) == dt("2026-12-31T23:59:59")
    assert ended_before(value, dt("2027-01-01T00:00:00Z"))


@pytest.mark.parametrize(
    ("value", "normalized"),
    [
        ("2026-12-31T23:30:00-01:00", "2027-01-01T00:30:00"),
        ("2027-01-01T00:30:00+01:00", "2026-12-31T23:30:00"),
        ("2026-07-17T12:30:00+0130", "2026-07-17T11:00:00"),
        ("2026-07-17T12:30:00-04", "2026-07-17T16:30:00"),
    ],
)
def test_non_utc_offsets_are_converted(value: str, normalized: str) -> None:
    assert parse_utc(value) == dt(normalized)
    interval = prefix_interval(value)
    assert interval.start == dt(normalized)
    assert interval.end == interval.start + timedelta(seconds=1)


@pytest.mark.parametrize(
    "value",
    [
        "2026Z",
        "2026-07Z",
        "2026-07-17Z",
        "2026-07-17T12+01:00",
        "2026-07-17T12:30-04:00",
    ],
)
def test_timezone_requires_second_precision(value: str) -> None:
    with pytest.raises(ValueError, match="second precision"):
        prefix_interval(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026-7",
        "2026-02-29",
        "2026-07-17junk",
        " 2026-07-17",
        "2026-07-17 ",
        "2026-07-17T12:30:45.123456",
    ],
)
def test_invalid_prefix_dates(value: str) -> None:
    with pytest.raises(ValueError):
        prefix_interval(value)
