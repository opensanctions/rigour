from datetime import datetime, timezone, date
from rigour.time import utc_now, utc_date


def test_utc_now():
    assert utc_now() is not None
    assert isinstance(utc_now(), datetime)
    assert utc_now().tzinfo == timezone.utc
    assert utc_date() is not None
    assert isinstance(utc_date(), date)
    assert utc_date() == utc_now().date()
