from datetime import datetime, timezone

from frontend.format_utils import format_relative_timestamp

NOW = datetime(2026, 7, 5, 21, 30, tzinfo=timezone.utc)


def test_less_than_a_minute_ago():
    ts = "2026-07-05T21:29:45+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "à l'instant"


def test_minutes_ago():
    ts = "2026-07-05T21:26:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "il y a 4 min"


def test_same_day_over_an_hour_ago():
    ts = "2026-07-05T09:14:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "aujourd'hui à 09:14"


def test_yesterday():
    ts = "2026-07-04T21:14:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "hier à 21:14"


def test_older_than_yesterday():
    ts = "2026-06-20T10:00:00+00:00"
    assert format_relative_timestamp(ts, now=NOW) == "20/06/2026 à 10:00"


def test_naive_iso_timestamp_is_treated_as_utc():
    ts = "2026-07-05T21:26:00"
    assert format_relative_timestamp(ts, now=NOW) == "il y a 4 min"
