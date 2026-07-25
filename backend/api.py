"""FastAPI REST API for Backstage UI integration."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.config import Config
from backend.core.store import MediaStore
from backend.core.models import Media

from backend.core.tmdb import TMDBClient

router = APIRouter(prefix="/api", tags=["medias"])


def get_store() -> MediaStore:
    return MediaStore(Config.DB_PATH)


class UpdateMediaRequest(BaseModel):
    rating: Optional[str] = None
    review: Optional[str] = None
    watched_in_cinema: Optional[bool] = None
    watched_date: Optional[str] = None
    status: Optional[str] = None
    support: Optional[str] = None
    is_favorite: Optional[bool] = None
    backdrop_url: Optional[str] = None
    cast: Optional[List[str]] = None
    categories: Optional[List[str]] = None


class RelinkTMDBRequest(BaseModel):
    tmdb_id: int


class CreateFromTMDBRequest(BaseModel):
    tmdb_id: int


@router.get("/tmdb/search")
async def search_tmdb(query: str):
    if not query or not query.strip():
        return []
    tmdb = TMDBClient()
    results = await tmdb.search_movie(query.strip())
    out = []
    for r in results:
        poster_url = tmdb.get_poster_url(r)
        backdrop_url = tmdb.get_backdrop_url(r)
        out.append({
            "tmdb_id": r["id"],
            "title": r.get("title") or r.get("original_title") or "",
            "release_date": r.get("release_date") or "",
            "poster_url": poster_url,
            "backdrop_url": backdrop_url,
            "overview": r.get("overview") or ""
        })
    return out


@router.post("/medias/{media_id}/relink_tmdb", response_model=Media)
async def relink_tmdb(
    media_id: str,
    payload: RelinkTMDBRequest,
    store: MediaStore = Depends(get_store),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    tmdb = TMDBClient()
    details = await tmdb.get_movie_details(payload.tmdb_id)
    if not details:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB pour cet ID")

    updates = {
        "title": details.get("title") or media.title,
        "cover_url": tmdb.get_poster_url(details) or media.cover_url,
        "backdrop_url": tmdb.get_backdrop_url(details) or media.backdrop_url,
        "cast": tmdb.get_cast(details, limit=5),
        "director": tmdb.get_director(details) or media.director,
        "synopsis": (details.get("overview") or media.synopsis)[:2000],
        "categories": tmdb.get_genres(details) or media.categories,
        "tmdb_ok": True,
    }
    if details.get("release_date"):
        updates["release_date"] = details["release_date"]

    await store.update(media_id, updates)
    refreshed = await store.fetch_one(media_id)
    return refreshed


@router.get("/medias", response_model=List[Media])
async def list_medias(store: MediaStore = Depends(get_store)):
    return await store.fetch_all()


@router.get("/medias/{media_id}", response_model=Media)
async def get_media(media_id: str, store: MediaStore = Depends(get_store)):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    return media


@router.post("/medias/from_tmdb", response_model=Media)
async def create_media_from_tmdb(
    payload: CreateFromTMDBRequest,
    store: MediaStore = Depends(get_store),
):
    tmdb = TMDBClient()
    details = await tmdb.get_movie_details(payload.tmdb_id)
    if not details:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB")
    return await store.create({
        "title": details.get("title") or details.get("original_title") or "Sans titre",
        "type": "Film",
        "status": "À regarder",
        "rating": None,
        "release_date": details.get("release_date") or None,
        "director": tmdb.get_director(details),
        "categories": tmdb.get_genres(details),
        "synopsis": (details.get("overview") or "")[:2000],
        "cover_url": tmdb.get_poster_url(details),
        "backdrop_url": tmdb.get_backdrop_url(details),
        "cast": tmdb.get_cast(details, limit=5),
        "tmdb_ok": True,
    })


@router.patch("/medias/{media_id}", response_model=Media)
async def update_media(
    media_id: str,
    payload: UpdateMediaRequest,
    store: MediaStore = Depends(get_store),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    update_fields: Dict[str, Any] = {}
    if payload.rating is not None:
        update_fields["rating"] = payload.rating
    if payload.review is not None:
        update_fields["review"] = payload.review
    if payload.watched_in_cinema is not None:
        update_fields["watched_in_cinema"] = payload.watched_in_cinema
    if payload.watched_date is not None:
        update_fields["watched_date"] = payload.watched_date
    if payload.status is not None:
        status = {"watched": "Terminé", "watchlist": "À regarder"}.get(payload.status, payload.status)
        update_fields["status"] = status
        if status == "À regarder":
            update_fields["rating"] = None
    if payload.support is not None:
        update_fields["support"] = payload.support
    if payload.backdrop_url is not None:
        update_fields["backdrop_url"] = payload.backdrop_url
    if payload.cast is not None:
        update_fields["cast"] = payload.cast
    if payload.categories is not None:
        update_fields["categories"] = payload.categories
    if payload.is_favorite is not None:
        tags = set(media.tags)
        if payload.is_favorite:
            tags.add("Favoris")
        else:
            tags.discard("Favoris")
        update_fields["tags"] = list(tags)

    if update_fields:
        await store.update(media_id, update_fields)
        media = await store.fetch_one(media_id)

    return media



@router.post("/medias/{media_id}/stream")
async def trigger_stream(media_id: str, store: MediaStore = Depends(get_store)):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    return {
        "status": "playing",
        "server": "HP ProDesk 600 G4",
        "media_id": media.id,
        "title": media.title,
        "stream_url": f"http://hp-prodesk.local:8090/stream/{media.id}.mkv",
        "message": f"Lecture de « {media.title} » lancée sur le serveur HP ProDesk."
    }
