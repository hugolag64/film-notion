from datetime import date, datetime, timezone

from backend.core.ics import CalendarEvent, build_calendar


def test_calendar_is_crlf_folded_and_escaped():
    text = build_calendar(
        [CalendarEvent("u1@b", date(2026, 12, 16), "🎬 Dune; partie 3, " + "é" * 60, "Au Grand Sud")],
        datetime(2026, 11, 26, tzinfo=timezone.utc),
    )

    assert text.startswith("BEGIN:VCALENDAR\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert "\n" not in text.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    assert "DTSTART;VALUE=DATE:20261216" in text and "DTEND;VALUE=DATE:20261217" in text
    unfolded = text.replace("\r\n ", "")
    assert "Dune\\; partie 3\\," in unfolded
    assert "é" * 60 in unfolded
    assert "DTSTAMP:20261126T000000Z" in text
    assert "PRODID:-//Backstage//Cinema//FR" in text


def test_newlines_and_backslashes_are_escaped():
    text = build_calendar(
        [CalendarEvent("u2@b", date(2026, 12, 1), "A\\B", "ligne 1\nligne 2")],
        datetime(2026, 11, 26, tzinfo=timezone.utc),
    )

    assert "SUMMARY:A\\\\B" in text
    assert "DESCRIPTION:ligne 1\\nligne 2" in text


def test_empty_calendar_is_still_valid():
    text = build_calendar([], datetime(2026, 11, 26, tzinfo=timezone.utc))

    assert text == (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Backstage//Cinema//FR\r\nCALSCALE:GREGORIAN\r\n"
        "X-WR-CALNAME:Backstage — Sorties ciné\r\nEND:VCALENDAR\r\n"
    )
