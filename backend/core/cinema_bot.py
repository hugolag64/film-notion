"""Bot « Ciné » du salon : répond aux commandes @ciné avec les horaires du Grand Sud."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, time, timedelta
from typing import Optional

from backend.core.cinema_store import CinemaStore
from backend.core.cinema_sync import BOT_ID, BOT_NAME, day_label, films_payload, reunion_now
from backend.core.store import MediaStore

STALE_AFTER = timedelta(days=2)
COMMANDS = [
    ("@ciné films", "Les films à l'affiche : clique sur un titre pour voir ses horaires."),
    ("@ciné ce soir", "Les séances d'aujourd'hui qui n'ont pas encore commencé."),
    ("@ciné demain", "Les séances de demain."),
    ("@ciné aide", "Cette liste de commandes."),
]

_COMMAND_RE = re.compile(r"^@cine(?=\s|$)(.*)$", re.DOTALL)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def parse_command(body: str) -> Optional[str]:
    match = _COMMAND_RE.match(_fold((body or "").strip()))
    if not match:
        return None
    argument = " ".join(match.group(1).split())
    if argument == "films":
        return "films"
    if argument in ("ce soir", "soir"):
        return "ce soir"
    if argument == "demain":
        return "demain"
    return "aide"


def _help_payload() -> dict:
    return {
        "type": "cine_help",
        "commands": [{"command": command, "description": description} for command, description in COMMANDS],
    }


def _stale_message(status: dict, now: datetime) -> Optional[str]:
    last = status["last_success_at"]
    if last is None:
        return "Horaires pas encore disponibles."
    if now - last > STALE_AFTER:
        return f"Horaires indisponibles depuis le {last:%d/%m}."
    return None


async def _day_reply(cinema: CinemaStore, start: datetime, end: datetime, header: str, empty: str):
    showtimes = await cinema.list_showtimes(start, end)
    if not showtimes:
        return empty, None
    films = await cinema.get_site_films()
    tracked = await cinema.tracked_tmdb_ids()
    by_film: dict[int, list[dict]] = {}
    for show in showtimes:
        if show["site_id"] in films:
            by_film.setdefault(show["site_id"], []).append(show)
    if not by_film:
        return empty, None
    lines = [header]
    payload_films = []
    for site_id, shows in by_film.items():  # ordre de la première séance
        film = films[site_id]
        times = ", ".join(f"{s['starts_at']:%H:%M} {s['version']}".strip() for s in shows)
        lines.append(f"• {film['title']} : {times}")
        payload_films.append({"site_id": site_id, "title": film["title"], "tracked": film["tmdb_id"] in tracked})
    return "\n".join(lines), films_payload(payload_films)


async def build_reply(command: str, cinema: CinemaStore, now: datetime) -> tuple[str, Optional[dict]]:
    if command == "aide":
        return "Commandes du bot Ciné :", _help_payload()
    stale = _stale_message(await cinema.get_status(), now)
    if stale:
        return stale, None
    if command == "films":
        showtimes = await cinema.list_showtimes(now)
        films = await cinema.get_site_films()
        tracked = await cinema.tracked_tmdb_ids()
        site_ids = {s["site_id"] for s in showtimes if s["site_id"] in films}
        if not site_ids:
            return "Aucune séance à venir au Grand Sud.", None
        listed = sorted(
            ({"site_id": sid, "title": films[sid]["title"], "tracked": films[sid]["tmdb_id"] in tracked}
             for sid in site_ids),
            key=lambda film: (_fold(film["title"]), film["site_id"]),
        )
        return "À l'affiche au Grand Sud :", films_payload(listed)
    midnight = datetime.combine(now.date() + timedelta(days=1), time())
    if command == "ce soir":
        return await _day_reply(cinema, now, midnight, "Ce soir au Grand Sud :", "Plus de séance ce soir au Grand Sud.")
    tomorrow = midnight.date()
    return await _day_reply(
        cinema, midnight, midnight + timedelta(days=1),
        f"Demain ({day_label(tomorrow)}) au Grand Sud :", "Aucune séance demain au Grand Sud.",
    )


async def handle_chat_message(
    body: str, store: MediaStore, now: Optional[datetime] = None, visible_to: Optional[str] = None,
) -> Optional[dict]:
    command = parse_command(body)
    if command is None:
        return None
    cinema = CinemaStore(store.db_path)
    reply, payload = await build_reply(command, cinema, now or reunion_now())
    return await store.create_chat_message(BOT_ID, BOT_NAME, None, reply, payload=payload, visible_to=visible_to)


async def film_showtimes(cinema: CinemaStore, site_id: int, now: datetime) -> Optional[dict]:
    film = (await cinema.get_site_films()).get(site_id)
    if film is None:
        return None
    days: list[dict] = []
    for show in await cinema.list_showtimes(now):
        if show["site_id"] != site_id:
            continue
        day = show["starts_at"].date()
        if not days or days[-1]["date"] != day.isoformat():
            days.append({"date": day.isoformat(), "label": day_label(day), "showtimes": []})
        days[-1]["showtimes"].append({
            "time": f"{show['starts_at']:%H:%M}",
            "version": show["version"],
            "booking_url": show["booking_url"],
        })
    return {
        "site_id": site_id,
        "title": film["title"],
        "stale": _stale_message(await cinema.get_status(), now) is not None,
        "days": days,
    }
