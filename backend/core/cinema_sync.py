"""Synchronisation quotidienne avec le site du Ciné Grand Sud.

Lit la programmation, relie les films à TMDB, enregistre les séances et
poste dans le salon les rappels des films suivis (présents dans une liste).
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

from backend.config import Config
from backend.core import http
from backend.core.cinema_reminders import compute_reminders
from backend.core.cinema_site import (
    GRAND_SUD_PATH,
    UPCOMING_PATH,
    FilmDetails,
    parse_film_page,
    parse_programme,
    parse_upcoming,
)
from backend.core.cinema_store import CinemaStore
from backend.core.store import MediaStore

logger = logging.getLogger(__name__)

REUNION = ZoneInfo("Indian/Reunion")
BOT_ID = "bot:cine"
BOT_NAME = "Ciné"
MATCH_RETRY = timedelta(days=7)
DETAILS_RETRY = timedelta(days=1)

_WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

Fetcher = Callable[[str], Awaitable[str]]


def reunion_now() -> datetime:
    """Heure actuelle à La Réunion, naïve, à la minute."""
    return datetime.now(REUNION).replace(tzinfo=None, second=0, microsecond=0)


def day_label(value: date) -> str:
    return f"{_WEEKDAYS[value.weekday()]} {value.day}/{value.month}"


def films_payload(films: list[dict]) -> dict:
    return {
        "type": "cine_films",
        "films": [
            {"site_id": film["site_id"], "title": film["title"], "tracked": bool(film.get("tracked"))}
            for film in films
        ],
    }


async def fetch_site_page(path: str) -> str:
    url = f"{Config.CINEMA_BASE_URL.rstrip('/')}{path}"
    response = await http.get_client().get(url, headers={"User-Agent": "Backstage"}, follow_redirects=True)
    if response.status_code != 200:
        raise RuntimeError(f"{url} a répondu {response.status_code}")
    return response.text


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def _result_year(result: dict) -> Optional[int]:
    value = (result.get("release_date") or "")[:4]
    return int(value) if value.isdigit() else None


async def match_tmdb(tmdb: Any, title: str, details: FilmDetails) -> Optional[int]:
    query = details.original_title or title
    year = details.release_national.year if details.release_national else None
    results = await tmdb.search_movie(query, year=year) if year else []
    if not results:
        results = await tmdb.search_movie(query)
    candidates = [
        r for r in results[:5]
        if isinstance(r.get("id"), int)
        and (year is None or (_result_year(r) is not None and abs(_result_year(r) - year) <= 1))
    ]
    if not candidates:
        return None
    wanted = {_fold(name) for name in details.directors if name}
    if wanted:
        for candidate in candidates:
            movie = await tmdb.get_movie_details(candidate["id"])
            director = tmdb.get_director(movie) if movie else None
            if director and _fold(director) in wanted:
                return candidate["id"]
    return candidates[0]["id"]


def _arrival_text(title: str, first: datetime) -> str:
    return f"🎬 {title} arrive au Grand Sud : première séance {day_label(first.date())} à {first:%H:%M}."


def _end_text(title: str, last: datetime) -> str:
    return f"⏳ Dernières séances de {title} au Grand Sud : jusqu'à {day_label(last.date())}."


async def refresh_cinema(
    store: MediaStore, cinema: CinemaStore, tmdb: Any, fetch: Fetcher, now: datetime,
) -> dict:
    first_run = (await cinema.get_status())["last_success_at"] is None

    try:
        programme = parse_programme(await fetch(GRAND_SUD_PATH))
        if not programme:
            raise RuntimeError("Programmation lue sans aucun film")
        if not any(film.showtimes for film in programme):
            raise RuntimeError("Programmation lue sans aucune séance")
    except Exception as exc:
        logger.warning("[cinema] Lecture de la programmation impossible : %s", exc)
        await cinema.record_failure(now, str(exc) or exc.__class__.__name__)
        return {"ok": False, "films": 0, "posted": 0}

    try:
        upcoming = parse_upcoming(await fetch(UPCOMING_PATH))
    except Exception as exc:
        logger.warning("[cinema] Lecture des prochaines sorties impossible : %s", exc)
        upcoming = []

    for film in [*programme, *upcoming]:
        await cinema.upsert_site_film(film.site_id, film.title, film.url, film.poster_url)

    # Seuls les films lus aujourd'hui : un film disparu du site n'est plus relu.
    seen = {film.site_id for film in programme} | {film.site_id for film in upcoming}
    films = await cinema.get_site_films()
    for site_id, film in films.items():
        if site_id not in seen:
            continue
        fetched_at = film["details_fetched_at"]
        stale = fetched_at is None or (not film["release_reunion"] and now - fetched_at > DETAILS_RETRY)
        if not stale:
            continue
        try:
            details = parse_film_page(await fetch(film["url"]))
        except Exception as exc:
            logger.warning("[cinema] Fiche du film %s illisible : %s", site_id, exc)
            continue
        await cinema.set_film_details(site_id, details, now)

    if tmdb is not None:
        films = await cinema.get_site_films()
        for site_id, film in films.items():
            attempted = film["match_attempted_at"]
            if site_id not in seen or film["tmdb_id"] is not None or (attempted is not None and now - attempted <= MATCH_RETRY):
                continue
            details = FilmDetails(
                film["original_title"],
                tuple(film["directors"]),
                date.fromisoformat(film["release_national"]) if film["release_national"] else None,
                date.fromisoformat(film["release_reunion"]) if film["release_reunion"] else None,
            )
            try:
                tmdb_id = await match_tmdb(tmdb, film["title"], details)
            except Exception as exc:
                logger.warning("[cinema] Association TMDB impossible pour %s : %s", site_id, exc)
                continue
            await cinema.set_tmdb_match(site_id, tmdb_id, now)

    await cinema.replace_showtimes({film.site_id: list(film.showtimes) for film in programme})

    films = await cinema.get_site_films()
    tracked_ids = await cinema.tracked_tmdb_ids()
    tracked_sites = {sid for sid, film in films.items() if film["tmdb_id"] in tracked_ids}
    reminders = compute_reminders(
        {film.site_id: [s.starts_at for s in film.showtimes] for film in programme},
        tracked_sites,
        await cinema.sent_reminders(),
        now,
        first_run,
    )
    posted = 0
    for reminder in reminders:
        title = films[reminder.site_id]["title"]
        if reminder.post:
            body = _arrival_text(title, reminder.first) if reminder.kind == "arrivee" else _end_text(title, reminder.last)
            payload = films_payload([{"site_id": reminder.site_id, "title": title, "tracked": True}])
            await store.create_chat_message(BOT_ID, BOT_NAME, None, body, payload=payload)
            posted += 1
        await cinema.record_reminder(reminder.site_id, reminder.kind, now)

    await cinema.record_success(now)
    return {"ok": True, "films": len(programme), "posted": posted}


async def refresh_tracked_release_dates(
    store: MediaStore, cinema: CinemaStore, tmdb: Any, today: date, limit: int = 40,
) -> int:
    from backend.journal_api import _movie_from_details

    tracked = sorted(await cinema.tracked_tmdb_ids())
    cached = await store.get_tmdb_movies(tracked)
    recent_limit = (today - timedelta(days=30)).isoformat()
    due = []
    for tmdb_id in tracked:
        movie = cached.get(tmdb_id)
        if movie is None:
            continue
        fetched = datetime.fromisoformat(movie["fetched_at"])
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age_days = (today - fetched.date()).days
        fr_date = movie.get("fr_release_date")
        if (not fr_date and age_days > 1) or (fr_date and age_days > 7 and fr_date >= recent_limit):
            due.append(tmdb_id)
    refreshed = 0
    for tmdb_id in due[:limit]:
        try:
            details = await tmdb.get_movie_details(tmdb_id)
        except Exception as exc:
            logger.warning("[cinema] Relecture TMDB impossible pour %s : %s", tmdb_id, exc)
            continue
        if not details:
            continue
        await store.upsert_tmdb_movie(_movie_from_details(tmdb_id, details, tmdb))
        refreshed += 1
    return refreshed
