"""Routes du cinéma : horaires d'un film du Grand Sud et agenda ICS des sorties."""

import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.api import get_store
from backend.auth_api import AuthContext, get_current_user
from backend.config import Config
from backend.core.cinema_bot import film_showtimes
from backend.core.cinema_store import CinemaStore
from backend.core.cinema_sync import reunion_now
from backend.core.ics import CalendarEvent, build_calendar
from backend.core.store import MediaStore

cinema_router = APIRouter(prefix="/api/cinema", tags=["cinema"], dependencies=[Depends(get_current_user)])
# Sans session : l'application d'agenda s'abonne avec le seul jeton secret.
calendar_feed_router = APIRouter(prefix="/api/cinema", tags=["cinema"])

AGENDA_HORIZON = timedelta(days=365)


@cinema_router.get("/films/{site_id}/showtimes")
async def get_film_showtimes(site_id: int, store: MediaStore = Depends(get_store)):
    detail = await film_showtimes(CinemaStore(store.db_path), site_id, reunion_now())
    if detail is None:
        raise HTTPException(status_code=404, detail="Film inconnu")
    return detail


async def calendar_events(store: MediaStore, cinema: CinemaStore, today: date) -> list[CalendarEvent]:
    tracked = sorted(await cinema.tracked_tmdb_ids())
    cached = await store.get_tmdb_movies(tracked)
    reunion_dates: dict[int, date] = {}
    for film in (await cinema.get_site_films()).values():
        if film["tmdb_id"] in cached and film["release_reunion"]:
            day = date.fromisoformat(film["release_reunion"])
            previous = reunion_dates.get(film["tmdb_id"])
            reunion_dates[film["tmdb_id"]] = min(day, previous) if previous else day
    oldest = today - AGENDA_HORIZON
    events = []
    for tmdb_id in tracked:
        movie = cached.get(tmdb_id)
        if movie is None:
            continue
        if tmdb_id in reunion_dates:
            day, description = reunion_dates[tmdb_id], "Au Grand Sud"
        elif movie.get("fr_release_date"):
            day, description = date.fromisoformat(movie["fr_release_date"]), "Date France, à confirmer pour La Réunion"
        else:
            continue
        if day < oldest:
            continue
        events.append(CalendarEvent(
            uid=f"backstage-cinema-{tmdb_id}@backstage",
            day=day,
            summary=f"🎬 {movie['title']} — sortie au cinéma",
            description=description,
        ))
    events.sort(key=lambda event: (event.day, event.uid))
    return events


def _calendar_url(token: str) -> dict:
    return {"url": f"{Config.BACKSTAGE_PUBLIC_URL.rstrip('/')}/api/cinema/agenda.ics?token={token}"}


@cinema_router.get("/calendar")
async def get_calendar_url(
    current: AuthContext = Depends(get_current_user), store: MediaStore = Depends(get_store),
):
    cinema = CinemaStore(store.db_path)
    token = await cinema.calendar_token_for(current.user["id"])
    if token is None:
        token = secrets.token_urlsafe(32)
        await cinema.set_calendar_token(current.user["id"], token)
    return _calendar_url(token)


@cinema_router.post("/calendar/regenerate")
async def regenerate_calendar_url(
    current: AuthContext = Depends(get_current_user), store: MediaStore = Depends(get_store),
):
    token = secrets.token_urlsafe(32)
    await CinemaStore(store.db_path).set_calendar_token(current.user["id"], token)
    return _calendar_url(token)


@calendar_feed_router.get("/agenda.ics")
async def calendar_feed(token: str = "", store: MediaStore = Depends(get_store)):
    cinema = CinemaStore(store.db_path)
    if not token or await cinema.user_for_calendar_token(token) is None:
        raise HTTPException(status_code=404)
    events = await calendar_events(store, cinema, reunion_now().date())
    return Response(
        content=build_calendar(events, datetime.now(timezone.utc)),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
