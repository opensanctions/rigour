from typing import Any

import pytest

from rigour.dates import ended_before, starts_after


def test_ended_before_prefix_precision() -> None:
    assert not ended_before("2026", "2026-07-17T12:00:00")
    assert ended_before("2026", "2027-01-01T00:00:00")

    assert not ended_before("2026-06", "2026-06-30T23:59:59")
    assert ended_before("2026-06", "2026-07-01T00:00:00")

    assert not ended_before("2026-06-15", "2026-06-15T23:59:59")
    assert ended_before("2026-06-15", "2026-06-16T00:00:00")

    assert not ended_before("2026-06-15T12", "2026-06-15T12:59:59")
    assert ended_before("2026-06-15T12", "2026-06-15T13:00:00")

    assert not ended_before("2026-06-15T12:30", "2026-06-15T12:30:59")
    assert ended_before("2026-06-15T12:30", "2026-06-15T12:31:00")

    assert not ended_before("2026-06-15T12:30:45", "2026-06-15T12:30:45.5")
    assert ended_before("2026-06-15T12:30:45", "2026-06-15T12:30:46")


def test_starts_after_boundaries() -> None:
    assert starts_after("2027", "2026-12-31T23:59:59")
    assert not starts_after("2027", "2027-01-01T00:00:00")
    assert starts_after("2068-07-16", "2026-07-17T12:00:00")
    assert not starts_after("2026", "2026-07-17T12:00:00")


def test_calendar_boundaries() -> None:
    assert ended_before("2024-02", "2024-03-01T00:00:00")
    assert ended_before("2024-02-29", "2024-03-01T00:00:00")
    assert ended_before("2026-12", "2027-01-01T00:00:00")


@pytest.mark.parametrize("suffix", ["Z", "+00", "+0000", "+00:00"])
def test_utc_suffixes(suffix: str) -> None:
    reference = f"2027-01-01T00:00:00{suffix}"
    assert ended_before("2026", reference)
    assert ended_before(f"2026-12-31T23:59:59{suffix}", reference)


@pytest.mark.parametrize("suffix", ["+01", "+0130", "+01:30", "-04:00"])
def test_non_utc_offsets_rejected(suffix: str) -> None:
    with pytest.raises(ValueError, match="naive or UTC"):
        ended_before("2026", f"2027-01-01T00:00:00{suffix}")
    with pytest.raises(ValueError, match="naive or UTC"):
        ended_before(f"2026-12-31T23:59:59{suffix}", "2027-01-01T00:00:00")


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
        "2026-07-17Z",
    ],
)
def test_invalid_prefix_dates(value: str) -> None:
    with pytest.raises(ValueError):
        ended_before(value, "2027-01-01T00:00:00")


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "2027",
        "2027-01-01",
        "2027-01-01T00:00",
        "2027-02-29T00:00:00",
        "2027-01-01T00:00:00junk",
        " 2027-01-01T00:00:00",
    ],
)
def test_invalid_references(reference: str) -> None:
    with pytest.raises(ValueError):
        ended_before("2026", reference)


@pytest.mark.parametrize("value", [None, 2026, [], object()])
def test_non_string_value_rejected(value: Any) -> None:
    with pytest.raises(TypeError, match="value must be a string"):
        ended_before(value, "2027-01-01T00:00:00")  # type: ignore[arg-type]


@pytest.mark.parametrize("reference", [None, 2026, [], object()])
def test_non_string_reference_rejected(reference: Any) -> None:
    with pytest.raises(TypeError, match="reference must be a string"):
        starts_after("2026", reference)  # type: ignore[arg-type]
