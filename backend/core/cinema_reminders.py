"""Décide quels rappels du salon envoyer : arrivée d'un film suivi, dernières séances.

Fonction pure : aucune E/S, l'heure courante est passée en paramètre.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

REMINDER_WINDOW_DAYS = 7
END_MARGIN_DAYS = 2


@dataclass(frozen=True)
class Reminder:
    site_id: int
    kind: str  # "arrivee" ou "fin"
    first: datetime
    last: datetime
    post: bool


def compute_reminders(
    showtimes: dict[int, list[datetime]],
    tracked_site_ids: set[int],
    sent: set[tuple[int, str]],
    now: datetime,
    first_run: bool,
) -> list[Reminder]:
    window_end = now + timedelta(days=REMINDER_WINDOW_DAYS)
    in_window = {
        site_id: sorted(t for t in times if now <= t < window_end)
        for site_id, times in showtimes.items()
    }
    in_window = {site_id: times for site_id, times in in_window.items() if times}
    if not in_window:
        return []
    window_last_day = max(times[-1].date() for times in in_window.values())

    reminders: list[Reminder] = []
    for site_id in sorted(in_window):
        if site_id not in tracked_site_ids:
            continue
        times = in_window[site_id]
        first, last = times[0], times[-1]
        arriving = (site_id, "arrivee") not in sent
        if arriving:
            reminders.append(Reminder(site_id, "arrivee", first, last, post=not first_run))
            continue
        if first_run or (site_id, "fin") in sent:
            continue
        if (window_last_day - last.date()).days >= END_MARGIN_DAYS:
            reminders.append(Reminder(site_id, "fin", first, last, post=True))
    return reminders
