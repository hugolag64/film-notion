"""Journal « Vu » (privé) et listes de films partagées entre colocs.

Les films sont identifiés par leur id TMDB et ne passent jamais par la table
`media` : seule une demande Seerr explicite fait entrer un film dans la
bibliothèque.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, field_validator

from backend.api import get_store
from backend.auth_api import AuthContext, get_current_user
from backend.core.mapping import is_series
from backend.core.models import DiaryEntry, Media
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient

journal_router = APIRouter(prefix="/api", tags=["journal"], dependencies=[Depends(get_current_user)])

TMDB_DOWN = "TMDB est injoignable, réessaie plus tard."


def _check_rating(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    if not 0.5 <= value <= 5 or (value * 2) != int(value * 2):
        raise ValueError("La note doit aller de 0,5 à 5 par demi-points.")
    return float(value)


def _check_watched_on(value: Optional[date]) -> Optional[date]:
    if value is not None and value > date.today():
        raise ValueError("La date de visionnage ne peut pas être dans le futur.")
    return value


class DiaryEntryCreate(BaseModel):
    tmdb_id: int
    watched_on: Optional[date] = None
    rating: Optional[float] = None
    review: Optional[str] = None
    in_cinema: bool = False

    _rating = field_validator("rating")(_check_rating)
    _watched_on = field_validator("watched_on")(_check_watched_on)


class DiaryEntryUpdate(BaseModel):
    watched_on: Optional[date] = None
    rating: Optional[float] = None
    review: Optional[str] = None
    in_cinema: Optional[bool] = None

    _rating = field_validator("rating")(_check_rating)
    _watched_on = field_validator("watched_on")(_check_watched_on)


def _movie_from_details(tmdb_id: int, details: Dict[str, Any], tmdb: Any) -> Dict[str, Any]:
    release_date = details.get("release_date") or None
    year = None
    if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
        year = int(release_date[:4])
    return {
        "tmdb_id": tmdb_id,
        "title": details.get("title") or details.get("original_title") or "Sans titre",
        "year": year,
        "release_date": release_date,
        "poster_url": tmdb.poster_url_from_path(details.get("poster_path")),
        "genres": [genre for genre in tmdb.get_genres(details) if genre],
    }


async def ensure_cached_movie(store: MediaStore, tmdb_id: int) -> dict:
    cached = (await store.get_tmdb_movies([tmdb_id])).get(tmdb_id)
    if cached:
        return cached
    try:
        tmdb = TMDBClient()
    except ValueError:
        raise HTTPException(status_code=502, detail=TMDB_DOWN)
    details = await tmdb.get_movie_details(tmdb_id)
    if not details:
        raise HTTPException(status_code=502, detail=TMDB_DOWN)
    return await store.upsert_tmdb_movie(_movie_from_details(tmdb_id, details, tmdb))


def _library_film(medias: list[Media], tmdb_id: int) -> Optional[Media]:
    for media in medias:
        if media.tmdb_id == tmdb_id and not is_series(media.type):
            return media
    return None


async def sync_library_state(store: MediaStore, user_id: str, tmdb_id: int) -> None:
    """Recopie le dernier visionnage dans l'état personnel du film de la bibliothèque."""
    media = _library_film(await store.fetch_all(), tmdb_id)
    if media is None:
        return
    latest = await store.latest_diary_entry(user_id, tmdb_id)
    if latest is None:
        return
    fields: Dict[str, Any] = {"status": "Terminé", "is_watchlist": False}
    if latest.rating is not None:
        fields["rating"] = f"{latest.rating:g}"
    await store.upsert_user_media_state(user_id, media.id, fields)


def _serialize_entry(entry: DiaryEntry, movie: Optional[dict], media_id: Optional[str]) -> dict:
    movie = movie or {}
    return {
        "id": entry.id,
        "tmdb_id": entry.tmdb_id,
        "watched_on": entry.watched_on.isoformat() if entry.watched_on else None,
        "rating": entry.rating,
        "review": entry.review,
        "in_cinema": entry.in_cinema,
        "source": entry.source,
        "created_at": entry.created_at.isoformat(),
        "movie": {
            "title": movie.get("title") or "Film inconnu",
            "year": movie.get("year"),
            "release_date": movie.get("release_date"),
            "poster_url": movie.get("poster_url"),
        },
        "media_id": media_id,
    }


async def _serialize_entries(store: MediaStore, entries: list[DiaryEntry]) -> list[dict]:
    movies = await store.get_tmdb_movies([entry.tmdb_id for entry in entries])
    medias = await store.fetch_all()
    media_ids = {}
    for media in medias:
        if media.tmdb_id is not None and not is_series(media.type):
            media_ids.setdefault(media.tmdb_id, media.id)
    return [_serialize_entry(entry, movies.get(entry.tmdb_id), media_ids.get(entry.tmdb_id)) for entry in entries]


async def _own_entry(store: MediaStore, entry_id: str, current: AuthContext) -> DiaryEntry:
    entry = await store.get_diary_entry(entry_id)
    if entry is None or entry.backstage_user_id != current.user["id"]:
        raise HTTPException(status_code=404, detail="Entrée introuvable")
    return entry


async def add_diary_entry(
    store: MediaStore, user_id: str, tmdb_id: int, *, watched_on: Optional[date],
    rating: Optional[float] = None, review: Optional[str] = None, in_cinema: bool = False,
    source: str = "manual",
) -> DiaryEntry:
    """Crée une entrée (film mis en cache au besoin) et synchronise la bibliothèque."""
    await ensure_cached_movie(store, tmdb_id)
    now = datetime.now(timezone.utc)
    entry = await store.create_diary_entry(DiaryEntry(
        id=str(uuid.uuid4()), backstage_user_id=user_id, tmdb_id=tmdb_id,
        watched_on=watched_on, rating=rating, review=review, in_cinema=in_cinema,
        source=source, created_at=now, updated_at=now,
    ))
    await sync_library_state(store, user_id, tmdb_id)
    return entry


@journal_router.get("/journal")
async def list_journal(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    entries = await store.list_diary_entries(current.user["id"])
    return {"entries": await _serialize_entries(store, entries)}


@journal_router.post("/journal", status_code=201)
async def create_journal_entry(
    payload: DiaryEntryCreate,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    watched_on = payload.watched_on if "watched_on" in payload.model_fields_set else date.today()
    entry = await add_diary_entry(
        store, current.user["id"], payload.tmdb_id, watched_on=watched_on,
        rating=payload.rating, review=payload.review, in_cinema=payload.in_cinema,
    )
    return (await _serialize_entries(store, [entry]))[0]


@journal_router.patch("/journal/{entry_id}")
async def update_journal_entry(
    entry_id: str,
    payload: DiaryEntryUpdate,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    entry = await _own_entry(store, entry_id, current)
    fields = {key: getattr(payload, key) for key in payload.model_fields_set}
    if "in_cinema" in fields and fields["in_cinema"] is None:
        fields.pop("in_cinema")
    updated = await store.update_diary_entry(entry.id, fields)
    await sync_library_state(store, current.user["id"], entry.tmdb_id)
    return (await _serialize_entries(store, [updated]))[0]


@journal_router.delete("/journal/{entry_id}", status_code=204)
async def delete_journal_entry(
    entry_id: str,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    entry = await _own_entry(store, entry_id, current)
    await store.delete_diary_entry(entry.id)
    return Response(status_code=204)
