"""Écriture d'un agenda iCalendar (RFC 5545) d'événements sur une journée."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

_CALENDAR_NAME = "Backstage — Sorties ciné"


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    day: date
    summary: str
    description: str


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Replie une ligne à 75 octets UTF-8 sans couper de caractère."""
    parts: list[str] = []
    current, size, limit = [], 0, 75
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            parts.append("".join(current))
            current, size, limit = [], 0, 74  # la suite commence par une espace
        current.append(char)
        size += width
    parts.append("".join(current))
    return [parts[0], *(" " + part for part in parts[1:])]


def build_calendar(events: list[CalendarEvent], now: datetime) -> str:
    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Backstage//Cinema//FR",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_escape(_CALENDAR_NAME)}",
    ]
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{event.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{event.day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(event.summary)}",
            f"DESCRIPTION:{_escape(event.description)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(part + "\r\n" for line in lines for part in _fold(line))
