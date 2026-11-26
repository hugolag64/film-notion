"""FastAPI REST API for Backstage UI integration."""
from datetime import datetime, timedelta, timezone
import asyncio
import logging
import random
import sqlite3
import time
import uuid
from random import Random
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

from backend.config import Config
from backend.core.store import MediaStore
from backend.core.models import (
    Media, Notification, RecommendationEvent, RecommendationEventType,
    RecommendationSession, Rental,
)

from backend.core.tmdb import TMDBClient
from backend.core.mapping import is_series
from backend.core.tmdb_relink import build_relink_updates
from backend.core.series_episodes import (
    build_series_view, ensure_series_metadata, fetch_tmdb_series, save_tmdb_series,
)
from backend.core.arr import RadarrClient, SonarrClient, MediaServerError
from backend.core.seerr import SeerrClient, SeerrDuplicateRequest
from backend.core.jellyfin import JellyfinClient
from backend.core.media_server import Availability, MediaServerService
from backend.core.dashboard import build_dashboard_payload
from backend.core.backup import create_backup, get_backup_health, get_backup_status, verify_backup
from backend.core.recommendation_explanations import build_guided_explanation, is_readable_title
from backend.core.recommendations import (
    GENRE_IDS, RecommendationCandidate, TasteProfile, apply_session_genre_delta, build_local_question,
    _rating_value, build_taste_profile, choose_from_top, record_compare_choice, score_candidate,
    score_recommendation_candidate,
)
from backend.core.gemini_recommendations import GeminiRecommendationGateway, SUPPORTED_QUESTION_AXES
from backend.core.guided_recommendations import apply_guided_answer, guided_question
from backend.auth_api import AuthContext, get_auth_store, get_current_user, get_jellyfin_client, require_admin
from backend.core.auth import AuthStore
from backend.core import cinema_bot
from backend.core.party_service import PartyService, is_party_command
from urllib.parse import quote, parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["medias"],
    dependencies=[Depends(get_current_user)],
)
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check():
    return {"status": "ok"}


@health_router.get("/health/backup")
async def backup_health_check():
    health = await asyncio.to_thread(
        get_backup_health, Config.BACKUP_DIR, max_age_hours=Config.BACKUP_MAX_AGE_HOURS,
    )
    if health["status"] != "ok":
        raise HTTPException(status_code=503, detail=health)
    return health


def _rewrite_hls_manifest(
    manifest: str, media_id: str, season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> str:
    rewritten = []
    for line in manifest.splitlines():
        if not line or line.startswith("#"):
            rewritten.append(line)
            continue
        parsed = urlsplit(line)
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() != "api_key"]
        resource = f"/api/medias/{quote(media_id, safe='')}/playback/resource/{quote(parsed.path, safe='/')}"
        playback_params = {}
        if season_number is not None and episode_number is not None:
            playback_params = {"season_number": season_number, "episode_number": episode_number}
        if query or playback_params:
            query = urlencode(query + list(playback_params.items()))
            resource += f"?{query}"
        rewritten.append(resource)
    return "\n".join(rewritten) + ("\n" if manifest.endswith("\n") else "")


def get_store() -> MediaStore:
    return MediaStore(Config.DB_PATH)


def _recommendation_quota(
    current: AuthContext,
    store: MediaStore,
    now: datetime,
) -> dict[str, Any]:
    if current.user.get("role") == "admin":
        return {"limit": None, "used": 0, "remaining": None, "unlimited": True}
    day_start = _recommendation_day_start(now)
    limit = max(0, Config.RECOMMENDATION_DAILY_LIMIT)
    used = store.count_recommendation_sessions_sync(current.user["id"], day_start)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "unlimited": False,
    }


def _recommendation_day_start(now: datetime) -> datetime:
    timezone_name = getattr(Config, "RECOMMENDATION_TIMEZONE", "Europe/Paris")
    local_now = now.astimezone(ZoneInfo(timezone_name))
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _gemini_gateway() -> GeminiRecommendationGateway:
    return GeminiRecommendationGateway(
        api_key=Config.GEMINI_API_KEY,
        model=Config.GEMINI_MODEL,
        max_output_tokens=Config.GEMINI_MAX_OUTPUT_TOKENS,
    )


def _gemini_cost_estimate(usage: dict[str, int]) -> float:
    return round(
        usage.get("input_tokens", 0) * 0.0000003
        + usage.get("output_tokens", 0) * 0.0000025,
        8,
    )


async def _record_gemini_usage(
    store: MediaStore,
    current: AuthContext,
    session_id: str,
    usage: dict[str, int],
) -> None:
    await store.record_recommendation_usage({
        "backstage_user_id": current.user["id"],
        "session_id": session_id,
        "model": Config.GEMINI_MODEL,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cost_estimate_usd": _gemini_cost_estimate(usage),
        "created_at": datetime.now(timezone.utc),
    })


async def _record_gemini_failure(
    store: MediaStore,
    current: AuthContext,
    session_id: str,
    error: Exception,
) -> None:
    await store.record_recommendation_usage({
        "backstage_user_id": current.user["id"],
        "session_id": session_id,
        "model": Config.GEMINI_MODEL,
        "status": "error",
        "error": type(error).__name__,
        "created_at": datetime.now(timezone.utc),
    })


async def _recommendation_profile(
    current: AuthContext,
    store: MediaStore,
) -> tuple[TasteProfile, list[RecommendationEvent]]:
    medias = await store.fetch_all()
    states = await store.list_user_media_states(current.user["id"])
    events = await store.list_recommendation_events(current.user["id"])
    playback = await store.list_resume_progress(current.user["id"]) + await store.list_recently_completed(current.user["id"])
    return build_taste_profile(medias, states, playback, events, datetime.now(timezone.utc)), events


def _recent_question_axes(events: list[RecommendationEvent]) -> list[str]:
    return [
        str(event.value).removeprefix("axis:")
        for event in events
        if event.event_type == "question_answered"
        and str(event.value or "").startswith("axis:")
        and str(event.value).removeprefix("axis:") in SUPPORTED_QUESTION_AXES
    ]


def _recent_question_plans(events: list[RecommendationEvent]) -> list[list[str]]:
    plans: dict[str, list[tuple[int, str]]] = {}
    for event in sorted(events, key=lambda item: (item.created_at, item.id)):
        value = str(event.value or "")
        if event.event_type != "question_answered" or not value.startswith("plan:") or not event.session_id:
            continue
        payload = value.removeprefix("plan:")
        index_text, separator, axis = payload.partition(":")
        if separator and index_text.isdigit():
            index = int(index_text)
        else:
            axis = payload
            index = len(plans.get(event.session_id, []))
        if axis in SUPPORTED_QUESTION_AXES:
            plans.setdefault(event.session_id, []).append((index, axis))
    return [
        [axis for _, axis in sorted(items)]
        for items in list(plans.values())[-4:]
    ]


def _fallback_question_plan(recent_axes: list[str]) -> list[str]:
    recent = set(recent_axes[-len(SUPPORTED_QUESTION_AXES):])
    fresh = [axis for axis in SUPPORTED_QUESTION_AXES if axis not in recent]
    return (fresh + [axis for axis in SUPPORTED_QUESTION_AXES if axis not in fresh])[:5]


def _vary_question_plan(plan: list[str], recent_plans: list[list[str]], recent_axes: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(axis for axis in plan if axis in SUPPORTED_QUESTION_AXES))
    if not normalized:
        return _fallback_question_plan(recent_axes)
    recent = [item for item in recent_plans[-4:] if item]
    recent_first_axes = {item[0] for item in recent if item}
    for offset in range(len(normalized)):
        candidate = normalized[offset:] + normalized[:offset]
        if candidate not in recent and candidate[0] not in recent_first_axes:
            return candidate
    return _fallback_question_plan(recent_axes)


def _planned_question(
    session: RecommendationSession,
    candidates: list[RecommendationCandidate],
    profile: TasteProfile,
    start_index: int,
) -> dict[str, Any] | None:
    plan = [str(axis) for axis in session.session_preferences.get("question_plan", [])]
    max_questions = min(5, len(plan))
    for index in range(start_index, max_questions):
        question = build_local_question(plan[index], candidates, profile, session.session_preferences)
        if question is None:
            continue
        question["question_index"] = index
        question["max_questions"] = max_questions
        session.session_preferences["question_index"] = index
        session.session_preferences["current_question_axis"] = plan[index]
        if question.get("axis") == "movie_compare" and question.get("type") == "compare":
            # Remembered so the answer handler can tell which genres were
            # picked vs. rejected once the choice comes back — see
            # _resolve_compare_choice and record_compare_choice.
            session.session_preferences["compare_pair"] = [
                {"tmdb_id": option.get("tmdb_id"), "genre_ids": option.get("genre_ids") or []}
                for option in question.get("options", [])
            ]
        return question
    return None


class UpdateMediaRequest(BaseModel):
    title: Optional[str] = None
    original_title: Optional[str] = None
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


class UpdatePersonalMediaRequest(BaseModel):
    rating: Optional[str] = None
    review: Optional[str] = None
    status: Optional[str] = None
    is_favorite: Optional[bool] = None
    is_watchlist: Optional[bool] = None


class RecommendationEventRequest(BaseModel):
    session_id: Optional[str] = None
    media_id: Optional[str] = None
    event_type: RecommendationEventType
    value: Optional[str] = None
    numeric_value: Optional[float] = None


class RecommendationAnswerRequest(BaseModel):
    answer: str
    value: Optional[str] = None
    media_id: Optional[str] = None
    question_index: Optional[int] = None
    choices: Optional[list[str]] = None


class RecommendationConfirmRequest(BaseModel):
    tmdb_id: int
    download: bool = True


class RecommendationWatchlistRequest(BaseModel):
    tmdb_id: int


class RelinkTMDBRequest(BaseModel):
    tmdb_id: int


class CreateFromTMDBRequest(BaseModel):
    tmdb_id: int


class UpdateEpisodeRequest(BaseModel):
    watched: bool


class EpisodeRef(BaseModel):
    season_number: int
    episode_number: int


class AcquisitionRequest(BaseModel):
    quality_profile_id: Optional[int] = None
    root_folder: Optional[str] = None
    language_profile_id: Optional[int] = None
    monitor: str = "all"
    # Series only: request some seasons and/or single episodes instead of everything.
    seasons: Optional[List[int]] = None
    episodes: Optional[List[EpisodeRef]] = None


class SeerrRequestCreate(BaseModel):
    tmdb_id: int
    media_type: str = "movie"
    quality_profile_id: Optional[int] = None
    root_folder: Optional[str] = None
    language_profile_id: Optional[int] = None
    monitor: str = "all"


class StorageProtectionRequest(BaseModel):
    protected: bool


MAX_ACTIVE_RENTALS = 5
MAX_QUEUED_RENTALS = 10
# A request or download is already running for these states: never send a second one.
IN_PROGRESS_STATES = {"requested", "searching", "downloading", "imported"}


def _rental_status_for(availability_state: str) -> str:
    """Map a download state (Radarr/Sonarr vocabulary) onto a rental status."""
    if availability_state == "available":
        return "available"
    if availability_state in {"downloading", "imported"}:
        return "downloading"
    return "requested"


def _serialize_rental(rental: Rental) -> dict[str, Any]:
    return rental.model_dump(mode="json")


def _serialize_notification(notification: Notification) -> dict[str, Any]:
    return notification.model_dump(mode="json")


def get_media_server_service(store: MediaStore = Depends(get_store)) -> MediaServerService:
    radarr = RadarrClient(Config.RADARR_URL, Config.RADARR_API_KEY) if Config.radarr_enabled() else None
    sonarr = SonarrClient(Config.SONARR_URL, Config.SONARR_API_KEY) if Config.sonarr_enabled() else None
    seerr = SeerrClient(Config.SEERR_URL, Config.SEERR_API_KEY) if Config.seerr_enabled() else None
    jellyfin = JellyfinClient(
        Config.JELLYFIN_URL, Config.JELLYFIN_API_KEY,
        server_id=Config.JELLYFIN_SERVER_ID,
    ) if Config.jellyfin_enabled() else None
    return MediaServerService(store, radarr=radarr, sonarr=sonarr, jellyfin=jellyfin, seerr=seerr)


async def _hydrate_seerr_requests(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill Seerr's compact request records with display metadata from TMDB."""
    if not requests:
        return []
    try:
        tmdb = TMDBClient()
    except ValueError:
        return requests

    async def hydrate(request: dict[str, Any]) -> dict[str, Any]:
        media = request.get("media") if isinstance(request.get("media"), dict) else {}
        tmdb_id = media.get("tmdbId", media.get("tmdb_id", request.get("mediaId")))
        if not tmdb_id:
            return request
        try:
            media_type = request.get("mediaType") or media.get("mediaType")
            is_series = media_type == "tv" or bool(media.get("tvdbId"))
            details = await tmdb.get_details(int(tmdb_id), is_series=is_series)
        except (TypeError, ValueError):
            details = None
        if not details:
            return request
        enriched_media = {
            **media,
            "title": media.get("title") or media.get("name") or details.get("title") or details.get("name"),
            "posterPath": media.get("posterPath") or media.get("poster_path") or details.get("poster_path"),
            "releaseDate": media.get("releaseDate") or media.get("release_date") or details.get("release_date") or details.get("first_air_date"),
        }
        return {**request, "media": enriched_media}

    return list(await asyncio.gather(*(hydrate(request) for request in requests)))


async def _prune_available_seerr_requests(seerr: SeerrClient, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove completed requests from Seerr and return only active queue items."""
    active = []
    for request in requests:
        media = request.get("media") if isinstance(request.get("media"), dict) else {}
        status = media.get("status")
        available = status == 5 or str(status).lower() in {"available", "completed"}
        if available and request.get("id") is not None:
            try:
                await seerr.cancel_request(request["id"])
            except (MediaServerError, RuntimeError, ValueError) as error:
                logger.warning("Suppression de la demande Seerr %s impossible: %s", request["id"], error)
            continue
        active.append(request)
    return active


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


async def search_tmdb_tv(query: str, tmdb: TMDBClient):
    if not query or not query.strip():
        return []
    results = await tmdb.search_tv(query.strip())
    return [{
        "tmdb_id": result["id"],
        "title": result.get("title") or result.get("name") or "",
        "release_date": result.get("release_date") or result.get("first_air_date") or "",
        "poster_url": tmdb.get_poster_url(result),
        "backdrop_url": tmdb.get_backdrop_url(result),
        "overview": result.get("overview") or "",
    } for result in results]


@router.get("/tmdb/search/tv")
async def search_tmdb_tv_endpoint(query: str):
    return await search_tmdb_tv(query, TMDBClient())


def _serialize_tmdb_movie_details(details: Dict[str, Any], tmdb: TMDBClient) -> Dict[str, Any]:
    return {
        "tmdb_id": details.get("id"),
        "title": details.get("title") or details.get("original_title") or "Sans titre",
        "original_title": details.get("original_title") or None,
        "overview": details.get("overview") or "",
        "release_date": details.get("release_date") or None,
        "runtime": details.get("runtime"),
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count") or 0,
        "poster_url": tmdb.get_poster_url(details),
        "backdrop_url": tmdb.get_backdrop_url(details),
        "director": tmdb.get_director(details),
        "genres": tmdb.get_genres(details),
        "cast": tmdb.get_cast(details, limit=8),
    }


@router.get("/tmdb/movies/{tmdb_id}")
async def get_tmdb_movie_preview(tmdb_id: int):
    tmdb = TMDBClient()
    details = await tmdb.get_movie_details(tmdb_id)
    if not details:
        raise HTTPException(status_code=404, detail="Film TMDB introuvable")
    return _serialize_tmdb_movie_details(details, tmdb)


@router.get("/tmdb/search/person")
async def search_tmdb_person_endpoint(query: str):
    if not query or len(query.strip()) < 2:
        return []
    tmdb = TMDBClient()
    results = await tmdb.search_person(query.strip())
    return [{
        "tmdb_id": result.get("id"),
        "name": result.get("name") or "",
        "known_for_department": result.get("known_for_department") or "",
        "profile_url": tmdb.poster_url_from_path(result.get("profile_path"), "w185"),
    } for result in results if result.get("id") and result.get("name")]


@router.post("/medias/{media_id}/relink_tmdb", response_model=Media, dependencies=[Depends(require_admin)])
async def relink_tmdb(
    media_id: str,
    payload: RelinkTMDBRequest,
    store: MediaStore = Depends(get_store),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    tmdb = TMDBClient()
    details = await tmdb.get_details(payload.tmdb_id, is_series=is_series(media.type))
    if not details:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB pour cet ID")

    await store.update(media_id, build_relink_updates(media, details, tmdb, payload.tmdb_id))
    refreshed = await store.fetch_one(media_id)
    return refreshed


_STATE_NOT_LOADED = object()


def get_catalogue_owner_id(auth_store: AuthStore = Depends(get_auth_store)) -> str | None:
    """The first administrator: the person whose ratings were saved on the
    catalogue itself before personal states existed."""
    for user in auth_store.list_users():
        if user["role"] == "admin":
            return user["id"]
    return None


def _seen_in_journal(media: Media, seen_tmdb_ids: set[int] | None) -> Media:
    # A film logged in the journal counts as seen, even if it reached the
    # server after the user watched it elsewhere. Only called when the user
    # has no personal state for it: a status they chose in the library wins.
    # Journal ids are TMDB *movie* ids, which overlap TV ids.
    if (
        seen_tmdb_ids and media.tmdb_id in seen_tmdb_ids and not is_series(media.type)
        and media.status not in {"Terminé", "Terminée"}
    ):
        return media.model_copy(update={"status": "Terminé", "is_watchlist": False})
    return media


async def _media_for_user(
    media: Media, current: AuthContext, store: MediaStore, state: Any = _STATE_NOT_LOADED,
    catalogue_owner_id: str | None = None, seen_tmdb_ids: set[int] | None = None,
) -> Media:
    if state is _STATE_NOT_LOADED:
        state = await store.get_user_media_state(current.user["id"], media.id)
    # Only the catalogue's original owner inherits the ratings stored on the
    # media; a second admin starts with a blank slate like everyone else.
    if state is None and current.user["role"] == "admin" and current.user["id"] == catalogue_owner_id:
        if media.rating and str(media.rating).strip():
            return media.model_copy(update={"status": "Terminé", "is_watchlist": False})
        return _seen_in_journal(media, seen_tmdb_ids)
    tags = [tag for tag in media.tags if tag != "Favoris"]
    if state and state.is_favorite:
        tags.append("Favoris")
    status = state.status if state else None
    is_watchlist = bool(state and state.is_watchlist)
    if state and state.rating and str(state.rating).strip():
        status = "Terminé"
        is_watchlist = False
    updates = {
        "status": status,
        "rating": state.rating if state else None,
        "review": state.review if state else None,
        "tags": tags,
        "is_watchlist": is_watchlist,
    }
    updated = media.model_copy(update=updates)
    return updated if state is not None else _seen_in_journal(updated, seen_tmdb_ids)


@router.get("/medias", response_model=List[Media])
async def list_medias(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
    catalogue_owner_id: str | None = Depends(get_catalogue_owner_id),
):
    medias, states, seen_tmdb_ids = await asyncio.gather(
        store.fetch_all(), store.list_user_media_states(current.user["id"]),
        store.list_diary_tmdb_ids(current.user["id"]),
    )
    # One query for every personal state instead of one per media.
    state_by_media = {state.media_id: state for state in states}
    return [
        await _media_for_user(
            media, current, store, state_by_media.get(media.id), catalogue_owner_id, seen_tmdb_ids,
        )
        for media in medias
    ]


@router.get("/library/available")
async def list_available_media(
    _: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    """Media ready on Jellyfin (playable now, or rentable instantly), plus every
    tracked media's download state so flatmates can see what is on its way.
    Only the state and progress are shared: paths and errors stay admin-only."""
    availabilities = await store.list_availabilities()
    return {
        "media_ids": [item.media_id for item in availabilities if item.jellyfin_id],
        "states": _states_from_availabilities(availabilities),
    }


def _states_from_availabilities(availabilities: list[Availability]) -> dict[str, dict]:
    return {
        item.media_id: {
            "state": item.state,
            "progress_percent": item.progress_percent,
            "ready": bool(item.jellyfin_id),
        }
        for item in availabilities
        # Deleted after a rental, revoked or dropped from Radarr: no longer on its way.
        if not (item.state == "error" and item.arr_id is None and not item.jellyfin_id)
    }


async def _library_states(store: MediaStore) -> dict[str, dict]:
    """Shared download/readiness state of every tracked media, keyed by media id."""
    return _states_from_availabilities(await store.list_availabilities())


@router.get("/dashboard")
async def dashboard_home(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    user_id = current.user["id"]
    service = get_media_server_service(store)
    medias, states, resume, completed, availabilities, rentals, notifications = await asyncio.gather(
        store.fetch_all(),
        store.list_user_media_states(user_id),
        store.list_resume_progress(user_id),
        store.list_recently_completed(user_id),
        store.list_availabilities(),
        store.list_user_rentals(user_id),
        store.list_notifications(user_id),
    )
    try:
        recommendations = [
            _serialize_recommendation(item)
            for item in await _recommendation_pool(current, store, {})
            if item is not None and item.score >= 0
        ]
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        logger.warning("Recommandations dashboard indisponibles: %s", error)
        recommendations = []
    requests = []
    if service.seerr and current.user.get("role") == "admin":
        try:
            requests = await service.seerr.list_requests(take=100, sort="modified", sort_direction="desc")
            requests = await _prune_available_seerr_requests(service.seerr, requests)
            requests = await _hydrate_seerr_requests(requests)
        except MediaServerError as error:
            logger.warning("Demandes Seerr dashboard indisponibles: %s", error)
    return build_dashboard_payload(
        medias, states, resume + completed, availabilities, rentals,
        notifications, recommendations, datetime.now(timezone.utc), requests,
    )


@router.post("/seerr/requests")
async def create_seerr_request(
    payload: SeerrRequestCreate,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    if not service.seerr:
        raise HTTPException(status_code=503, detail="Les demandes de films sont indisponibles pour le moment (service de demandes non configuré). Préviens l'administrateur.")
    if payload.media_type not in {"movie", "tv"}:
        raise HTTPException(status_code=422, detail="Type de média Seerr invalide")
    if payload.media_type == "movie":
        # Create the catalogue row and send its configured profile to Seerr only
        # after the user confirms the request. Roll back a new row if Seerr rejects it.
        existing = next((item for item in await service.store.fetch_all()
                         if item.type == "Film" and item.tmdb_id == payload.tmdb_id), None)
        media = await _find_or_create_movie(service.store, payload.tmdb_id)
        try:
            return await _acquire_media(media, AcquisitionRequest(
                quality_profile_id=payload.quality_profile_id,
                root_folder=payload.root_folder,
                language_profile_id=payload.language_profile_id,
                monitor=payload.monitor,
            ), current, service)
        except HTTPException:
            if existing is None:
                await service.store.delete(media.id)
            raise
    if current.user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Demande cette série à l'administrateur")
    try:
        return await service.seerr.request_media(
            tmdb_id=payload.tmdb_id,
            media_type="Film" if payload.media_type == "movie" else "Série",
            quality_profile_id=None,
            root_folder=None,
            language_profile_id=None,
            monitor="all",
        )
    except SeerrDuplicateRequest:
        return {"already_requested": True}
    except (MediaServerError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.delete("/seerr/requests/{request_id}", dependencies=[Depends(require_admin)])
async def cancel_seerr_request(
    request_id: int,
    service: MediaServerService = Depends(get_media_server_service),
):
    if not service.seerr:
        raise HTTPException(status_code=503, detail="Les demandes de films sont indisponibles pour le moment (service de demandes non configuré). Préviens l'administrateur.")
    try:
        await service.seerr.cancel_request(request_id)
    except (MediaServerError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"cancelled": True, "request_id": request_id}


@router.post("/recommendations/watchlist", response_model=Media)
async def add_recommendation_to_watchlist(
    payload: RecommendationWatchlistRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
    catalogue_owner_id: str | None = Depends(get_catalogue_owner_id),
):
    media = next(
        (item for item in await store.fetch_all() if item.type == "Film" and item.tmdb_id == payload.tmdb_id),
        None,
    )
    if media is None:
        tmdb = TMDBClient()
        details = await tmdb.get_movie_details(payload.tmdb_id)
        if not details:
            raise HTTPException(status_code=400, detail="Impossible de récupérer ce film")
        media = await store.create({
            "title": details.get("title") or details.get("original_title") or "Sans titre",
            "original_title": details.get("original_title") or None,
            "type": "Film", "status": "À regarder", "rating": None,
            "release_date": details.get("release_date") or None,
            "director": tmdb.get_director(details), "categories": tmdb.get_genres(details),
            "synopsis": (details.get("overview") or "")[:2000],
            "cover_url": tmdb.get_poster_url(details), "backdrop_url": tmdb.get_backdrop_url(details),
            "cast": tmdb.get_cast(details, limit=5), "tmdb_ok": True, "tmdb_id": payload.tmdb_id,
        })
    await store.upsert_user_media_state(current.user["id"], media.id, {
        "status": "À regarder", "is_watchlist": True,
    })
    return await _media_for_user(media, current, store, catalogue_owner_id=catalogue_owner_id)


@router.get("/medias/{media_id}", response_model=Media)
async def get_media(
    media_id: str,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
    catalogue_owner_id: str | None = Depends(get_catalogue_owner_id),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    seen_tmdb_ids = await store.list_diary_tmdb_ids(current.user["id"])
    return await _media_for_user(
        media, current, store, catalogue_owner_id=catalogue_owner_id, seen_tmdb_ids=seen_tmdb_ids,
    )


@router.get("/medias/{media_id}/tmdb-rating")
async def get_tmdb_rating(media_id: str, store: MediaStore = Depends(get_store)):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    try:
        from backend.core.tmdb_relink import select_confident_match

        tmdb = TMDBClient()
        tmdb_id = media.tmdb_id
        was_unlinked = not tmdb_id
        if not tmdb_id and media.type == "Film":
            year = media.release_date.year if media.release_date else None
            match = select_confident_match(media, await tmdb.search_movie(media.title, year=year))
            tmdb_id = int(match["id"]) if match and match.get("id") else None
            details = await tmdb.get_movie_details(tmdb_id) if tmdb_id else None
            if tmdb_id and details:
                await store.update(media.id, {"tmdb_ok": True, "tmdb_id": tmdb_id})
        else:
            details = await tmdb.get_movie_details(tmdb_id) if tmdb_id else None
    except Exception as error:
        logger.warning("Note TMDB indisponible pour le média %s : %s", media_id, error)
        return {"rating": None}
    raw_rating = details.get("vote_average") if details else None
    try:
        rating = float(raw_rating) if raw_rating is not None else None
    except (TypeError, ValueError):
        rating = None
    runtime = details.get("runtime") if details else None
    return {
        "rating": rating,
        **({"runtime": runtime} if isinstance(runtime, int) and runtime > 0 else {}),
        **({"tmdb_id": tmdb_id} if was_unlinked and tmdb_id else {}),
    }


@router.patch("/medias/{media_id}/personal", response_model=Media)
async def update_personal_media(
    media_id: str,
    payload: UpdatePersonalMediaRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
    catalogue_owner_id: str | None = Depends(get_catalogue_owner_id),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    fields = payload.model_dump(exclude_none=True)
    if fields.get("status") == "watched":
        fields["status"] = "Terminé"
    elif fields.get("status") == "watchlist":
        fields["status"] = "À regarder"
    if fields.get("rating") is not None and str(fields["rating"]).strip():
        fields["status"] = "Terminé"
        fields["is_watchlist"] = False
    elif fields.get("status") == "À regarder":
        fields["rating"] = None
    await store.upsert_user_media_state(current.user["id"], media_id, fields)
    if media.tmdb_id and media.type == "Film" and fields.get("status") == "Terminé":
        await _log_library_watch(store, current.user["id"], media.tmdb_id, fields)
    return await _media_for_user(media, current, store, catalogue_owner_id=catalogue_owner_id)


async def _log_library_watch(store: MediaStore, user_id: str, tmdb_id: int, fields: Dict[str, Any]) -> None:
    """Mirror a library rating into the journal without inventing a rewatch.

    Correcting a rating updates the most recent entry; only a film never
    logged before gets a new entry dated today.
    """
    from backend.journal_api import add_diary_entry, local_today

    changes: Dict[str, Any] = {}
    if "rating" in fields:
        changes["rating"] = _journal_rating(fields["rating"])
    if fields.get("review") is not None:
        changes["review"] = fields["review"]
    latest = await store.latest_diary_entry(user_id, tmdb_id)
    if latest is not None:
        if changes:
            await store.update_diary_entry(latest.id, changes)
        return
    try:
        await add_diary_entry(
            store, user_id, tmdb_id, watched_on=local_today(),
            rating=changes.get("rating"), review=changes.get("review"), source="library",
        )
    except HTTPException as error:
        logger.warning("Entrée de journal non créée pour le film TMDB %s : %s", tmdb_id, error.detail)


def _journal_rating(raw: Any) -> float | None:
    value = _rating_value(raw)
    if value is None:
        return None
    return min(5.0, max(0.5, round(value * 2) / 2))


async def _log_already_seen(store: MediaStore, user_id: str, value: Any) -> None:
    """« Déjà vu » sur une recommandation : une entrée sans date ni note."""
    if not str(value or "").isdigit():
        return
    tmdb_id = int(value)
    if await store.latest_diary_entry(user_id, tmdb_id) is not None:
        return
    from backend.journal_api import add_diary_entry

    try:
        await add_diary_entry(store, user_id, tmdb_id, watched_on=None, source="recommendation")
    except HTTPException as error:
        logger.warning("Entrée de journal non créée pour le film TMDB %s : %s", tmdb_id, error.detail)


_POOL_SORT_OPTIONS = ("popularity.desc", "vote_average.desc", "vote_count.desc")
_RECENT_ERA_YEARS = 6
_CLASSIC_ERA_CUTOFF_YEAR = 2005
_TOP_PROFILE_GENRES = 3
_TMDB_IMAGE_PREFIXES = ("https://image.tmdb.org/t/p/w500", "https://image.tmdb.org/t/p/w1280")
# A watchlisted title has no locally stored TMDB score; a mildly-above-neutral
# default keeps it from being silently buried behind unrated TMDB popularity
# results purely for lacking a vote_average.
_WATCHLIST_CANDIDATE_VOTE_AVERAGE = 6.5


def _pool_seed(session_preferences: dict[str, Any]) -> dict[str, Any]:
    """Pick the TMDB discover page/sort once per session and persist it in
    session_preferences, instead of always fetching page 1 sorted by
    popularity — which returned the same ~20 films to every session."""
    seed = session_preferences.get("pool_seed")
    if isinstance(seed, dict) and "page" in seed and "sort_by" in seed:
        return seed
    seed = {"page": random.randint(1, 5), "sort_by": random.choice(_POOL_SORT_OPTIONS)}
    session_preferences["pool_seed"] = seed
    return seed


def _steer_pool_params(
    session_preferences: dict[str, Any], profile: TasteProfile, now: datetime,
) -> dict[str, Any]:
    """Turn the session's answers (and, failing that, the durable taste
    profile) into TMDB discover filters — so answering "Comédie" actually
    searches for comedies instead of only re-ranking whatever page 1 held."""
    params: dict[str, Any] = {}
    answered_genre = session_preferences.get("genre")
    selected_genres = session_preferences.get("genres", [])
    if selected_genres:
        params["with_genres"] = [GENRE_IDS[name] for name in selected_genres if name in GENRE_IDS]
    elif answered_genre and answered_genre in GENRE_IDS:
        params["with_genres"] = [GENRE_IDS[answered_genre]]
    elif session_preferences.get("discovery") != "surprise":
        liked_genres = sorted(
            (item for item in profile.genre_affinity.items() if item[1] > 0 and item[0] in GENRE_IDS),
            key=lambda item: -item[1],
        )[:_TOP_PROFILE_GENRES]
        if liked_genres:
            params["with_genres"] = [GENRE_IDS[name] for name, _ in liked_genres]
    era = session_preferences.get("era")
    if era == "recent":
        params["release_date_gte"] = f"{now.year - _RECENT_ERA_YEARS}-01-01"
    elif era == "classic":
        params["release_date_lte"] = f"{_CLASSIC_ERA_CUTOFF_YEAR}-12-31"
    if session_preferences.get("runtime_max"):
        params["runtime_max"] = session_preferences["runtime_max"]
    if session_preferences.get("mode") == "guided":
        params.setdefault("release_date_lte", now.date().isoformat())
    return params


def _tmdb_path_from_stored_url(url: str | None) -> str | None:
    """Backstage stores full TMDB image URLs on Media; recommendation
    candidates carry raw TMDB paths. Strip the known size prefix back off so a
    locally-sourced candidate's poster renders the same way a TMDB one does."""
    if not url:
        return None
    for prefix in _TMDB_IMAGE_PREFIXES:
        if url.startswith(prefix):
            return url[len(prefix):]
    return None


def _watchlist_candidate(media: Media) -> dict[str, Any]:
    """Shape a locally catalogued watchlist item like a TMDB discover result
    so it can be scored and shown as a candidate in its own right, instead of
    only ever acting as a scoring bonus for titles TMDB happened to surface."""
    return {
        "tmdb_id": media.tmdb_id,
        "title": media.title,
        "overview": media.synopsis or "",
        "genre_ids": [GENRE_IDS[name] for name in media.categories if name in GENRE_IDS],
        "release_date": media.release_date.isoformat() if media.release_date else None,
        "vote_average": _WATCHLIST_CANDIDATE_VOTE_AVERAGE,
        "poster_path": _tmdb_path_from_stored_url(media.cover_url),
        "backdrop_path": _tmdb_path_from_stored_url(media.backdrop_url),
    }


def _resolve_compare_choice(
    compare_pair: list[dict[str, Any]] | None, picked_tmdb_id: int,
) -> tuple[list[int], list[int]] | None:
    """Given the two options shown for a movie_compare question and which one
    was picked, return (picked_genre_ids, rejected_genre_ids) — or None when
    the stored pair is missing, stale, or doesn't include the picked id."""
    if not compare_pair or len(compare_pair) != 2:
        return None
    picked = next((option for option in compare_pair if option.get("tmdb_id") == picked_tmdb_id), None)
    rejected = next((option for option in compare_pair if option.get("tmdb_id") != picked_tmdb_id), None)
    if picked is None or rejected is None:
        return None
    return picked.get("genre_ids") or [], rejected.get("genre_ids") or []


async def _recommendation_pool(
    current: AuthContext,
    store: MediaStore,
    session_preferences: dict[str, Any],
) -> list[RecommendationCandidate]:
    user_id = current.user["id"]
    medias = await store.fetch_all()
    states = await store.list_user_media_states(user_id)
    events = await store.list_recommendation_events(user_id)
    playback = await store.list_resume_progress(user_id) + await store.list_recently_completed(user_id)
    now = datetime.now(timezone.utc)
    profile = build_taste_profile(medias, states, playback, events, now)
    # A movie_compare pick nudges genres for the rest of THIS session only —
    # the durable, cross-session profile above is never mutated.
    profile = apply_session_genre_delta(profile, session_preferences, now)
    seed = _pool_seed(session_preferences)
    steer = _steer_pool_params(session_preferences, profile, now)
    guided = session_preferences.get("mode") == "guided"
    try:
        tmdb = TMDBClient()
        pages = [seed["page"]]
        if guided:
            pages.append(2 if seed["page"] == 1 else 1)
        batches = await asyncio.gather(*(tmdb.discover_movies(
            page=page, sort_by=seed["sort_by"], min_vote_count=25, **steer,
        ) for page in pages))
        candidates = list({candidate["tmdb_id"]: candidate for batch in batches for candidate in batch}.values())
    except (ValueError, httpx.HTTPError):
        return []
    state_by_media = {state.media_id: state for state in states}
    shown_tmdb_ids = {
        int(value) for value in session_preferences.get("shown_tmdb_ids", [])
        if str(value).isdigit()
    }
    seen_tmdb_ids = {
        media.tmdb_id
        for media in medias
        if media.tmdb_id and (
            state_by_media.get(media.id, None) and (
                state_by_media[media.id].status in {"Terminé", "Terminée"}
                or bool(state_by_media[media.id].rating and str(state_by_media[media.id].rating).strip())
            )
            or any(progress.media_id == media.id and (progress.played or progress.percent >= 95) for progress in playback)
        )
    }
    seen_tmdb_ids.update(shown_tmdb_ids)
    hard_seen_tmdb_ids = set(seen_tmdb_ids)
    recent_cutoff = now - timedelta(days=max(0, Config.RECOMMENDATION_RECENT_DAYS))
    recent_shown_tmdb_ids = {
        int(event.value) for event in events
        if event.event_type == "shown"
        and event.created_at >= recent_cutoff
        and str(event.value or "").isdigit()
    }
    hard_reject_media_ids = {event.media_id for event in events if event.event_type == "hard_reject" and event.media_id}
    hard_reject_tmdb_ids = {
        media.tmdb_id for media in medias if media.id in hard_reject_media_ids and media.tmdb_id
    }
    hard_reject_tmdb_ids.update(
        int(event.value) for event in events
        if event.event_type == "hard_reject" and str(event.value or "").isdigit()
    )
    already_seen_tmdb_ids = {
        int(event.value) for event in events
        if event.event_type == "already_seen" and str(event.value or "").isdigit()
    }
    seen_tmdb_ids.update(already_seen_tmdb_ids)
    hard_seen_tmdb_ids.update(already_seen_tmdb_ids)
    journal_tmdb_ids = await store.list_diary_tmdb_ids(user_id)
    seen_tmdb_ids.update(journal_tmdb_ids)
    hard_seen_tmdb_ids.update(journal_tmdb_ids)
    seen_tmdb_ids.update(recent_shown_tmdb_ids)
    temporary_negative_tmdb_ids: dict[int, float] = {}
    for event in events:
        if event.event_type not in {"not_now", "less_like_this"} or not str(event.value or "").isdigit():
            continue
        expires_at = event.created_at + timedelta(days=14 if event.event_type == "not_now" else 45)
        if expires_at > now:
            tmdb_id = int(event.value)
            temporary_negative_tmdb_ids[tmdb_id] = max(
                temporary_negative_tmdb_ids.get(tmdb_id, 0),
                0.12 if event.event_type == "not_now" else 0.25,
            )
    watchlisted_tmdb_ids = {
        media.tmdb_id
        for media in medias
        if media.tmdb_id and state_by_media.get(media.id) and (
            state_by_media[media.id].is_watchlist or state_by_media[media.id].is_favorite
        )
    }
    # A watchlisted title only TMDB discover doesn't happen to surface would
    # otherwise never be a candidate at all — bonus scoring alone can't fix
    # that if the title never enters the pool in the first place.
    local_tmdb_ids = set(watchlisted_tmdb_ids)
    if guided:
        ready_ids = {item.media_id for item in await store.list_availabilities() if item.jellyfin_id}
        local_tmdb_ids.update(media.tmdb_id for media in medias if media.id in ready_ids)
    already_fetched_ids = {candidate["tmdb_id"] for candidate in candidates}
    genre_filter = set(steer.get("with_genres", [])) if session_preferences.get("genres") else set()
    local_candidates = {}
    for media in medias:
        if not media.tmdb_id or media.tmdb_id not in local_tmdb_ids or media.tmdb_id in already_fetched_ids:
            continue
        if guided and (media.type != "Film" or media.tmdb_id in hard_seen_tmdb_ids | hard_reject_tmdb_ids):
            continue
        candidate = _watchlist_candidate(media)
        if guided:
            # Locally catalogued films do not store the TMDB community score.
            candidate["vote_average"] = 0
        if not genre_filter or genre_filter.intersection(candidate["genre_ids"]):
            local_candidates.setdefault(media.tmdb_id, candidate)
    if runtime_max := steer.get("runtime_max"):
        # TMDB Discover already checked the runtime of its results. Verify it
        # separately for titles injected from the local catalog.
        local_items = list(local_candidates.values())[:12]
        semaphore = asyncio.Semaphore(4)

        async def fits_runtime(candidate: dict[str, Any]) -> bool:
            async with semaphore:
                details = await tmdb.get_movie_details(candidate["tmdb_id"])
            runtime = (details or {}).get("runtime")
            if details:
                candidate["vote_average"] = details.get("vote_average") or 0
            return isinstance(runtime, int) and 0 < runtime <= runtime_max

        fits = await asyncio.gather(*(fits_runtime(item) for item in local_items))
        candidates.extend(item for item, valid in zip(local_items, fits) if valid)
    else:
        candidates.extend(local_candidates.values())

    def score_pool(excluded_ids: set[int]) -> list[RecommendationCandidate]:
        return [
            score_recommendation_candidate(
                candidate, profile, session_preferences,
                {"seen_tmdb_ids": excluded_ids, "watchlisted_tmdb_ids": watchlisted_tmdb_ids,
                 "hard_reject_tmdb_ids": hard_reject_tmdb_ids,
                 "temporary_negative_tmdb_ids": temporary_negative_tmdb_ids}, now,
            )
            for candidate in candidates
        ]

    scored = score_pool(seen_tmdb_ids)
    if recent_shown_tmdb_ids and sum(item.score >= 0 for item in scored) < (6 if guided else 2):
        # A cooldown is a soft memory, never a reason to show an empty screen.
        scored = score_pool(hard_seen_tmdb_ids)
    # A title the household cannot read (no French title on TMDB) is not a
    # usable suggestion, whatever its score.
    return [item for item in scored if is_readable_title(item.title)]


def _serialize_recommendation(candidate: RecommendationCandidate | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    payload = candidate.model_dump(mode="json")
    explanation = getattr(candidate, "explanation", None)
    if explanation:
        payload["explanation"] = explanation
    return payload


async def _guided_results(
    current: AuthContext, store: MediaStore, session: RecommendationSession, preferences: dict,
) -> list[dict]:
    ranked = sorted(
        (item for item in await _recommendation_pool(current, store, preferences) if item.score >= 0),
        key=lambda item: item.score, reverse=True,
    )
    if not ranked:
        return []
    medias, availabilities = await asyncio.gather(store.fetch_all(), store.list_availabilities())
    local = {media.tmdb_id: media.id for media in medias if media.type == "Film" and media.tmdb_id}
    availability_by_id = {row.media_id: row for row in availabilities}
    ready, other = [], []
    for item in ranked:
        media_id = local.get(item.tmdb_id)
        availability = availability_by_id.get(media_id)
        action = "request"
        if availability and availability.jellyfin_id:
            if len(ready) >= 15:
                continue
            try:
                await _ensure_playback_access(current, media_id, store)
            except HTTPException as error:
                if error.status_code not in {403, 404}:
                    raise
                action = "rent" if error.status_code == 403 else "request"
            else:
                action = "play"
        elif availability and availability.state in IN_PROGRESS_STATES:
            action = "pending"
        # Already on the server: playable now, or after an instant rental.
        on_server = bool(availability and availability.jellyfin_id) and action in {"play", "rent"}
        result = {
            **_serialize_recommendation(item), "media_id": media_id, "action": action,
            "ready_tonight": on_server,
        }
        if on_server:
            ready.append(result)
        elif len(other) < 15:
            other.append(result)
        if len(ready) >= 15 and len(other) >= 15:
            break
    # Keep both immediately playable titles and fresh discoveries in the
    # selection, even when the library already has many matches.
    pool = ready[:8] + other[:max(7, 15 - len(ready))] + ready[8:]
    pool = pool[:15]
    reasons: dict[int, str] = {}
    gateway = _gemini_gateway()
    if gateway.enabled and len(pool) > 1:
        try:
            reasons, usage = await asyncio.to_thread(gateway.rank_guided_films, preferences["answers"], pool)
            await _record_gemini_usage(store, current, session.id, usage)
        except Exception as error:
            await _record_gemini_failure(store, current, session.id, error)
    model_positions = {tmdb_id: index for index, tmdb_id in enumerate(reasons)}
    for item in pool:
        if reason := reasons.get(item["tmdb_id"]):
            item["explanation"] = reason
        else:
            # No LLM reason: explain from the user's own answers rather than
            # with a generic sentence.
            item["explanation"] = build_guided_explanation(item, preferences)
    pool.sort(key=lambda item: (
        item["action"] != "play", not item["ready_tonight"],
        model_positions.get(item["tmdb_id"], len(model_positions)),
    ))
    # At most two immediate picks at the top. Offer some contrasting options
    # before listing the rest of a large local library.
    ready = [item for item in pool if item["ready_tonight"]]
    other = [item for item in pool if not item["ready_tonight"]]
    return ready[:2] + other[:4] + ready[2:] + other[4:]


def _guided_response(session_id: str, *, question: dict | None = None, results: list[dict] | None = None) -> dict:
    return {
        "session_id": session_id, "state": "question" if question else "result" if results else "empty",
        "question": question, "result": results[0] if results else None, "results": results or [],
    }


async def _answer_guided_recommendation(
    session: RecommendationSession, payload: RecommendationAnswerRequest, current: AuthContext, store: MediaStore,
) -> dict:
    preferences = session.session_preferences
    if session.status == "completed" and "results" in preferences:
        return _guided_response(session.id, results=preferences["results"])
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Cette session est déjà terminée")
    index = session.question_count
    question = guided_question(preferences, index)
    if not question:
        raise HTTPException(status_code=409, detail="La sélection est en cours. Réessaie dans un instant.")
    if payload.question_index is not None and payload.question_index < index:
        return _guided_response(session.id, question=question)
    if payload.question_index != index or payload.choices is None:
        raise HTTPException(status_code=422, detail="Cette réponse ne correspond pas à la question")
    try:
        preferences = apply_guided_answer(preferences, question, payload.choices)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    next_question = guided_question(preferences, index + 1)
    if not await store.advance_recommendation_session(session.id, index, preferences):
        raise HTTPException(status_code=409, detail="Cette réponse a déjà été traitée")
    if next_question:
        return _guided_response(session.id, question=next_question)

    try:
        results = await _guided_results(current, store, session, preferences)
    except Exception:
        logger.exception("Sélection de films indisponible pour la session %s", session.id)
        await store.update_recommendation_session(session.id, {"status": "cancelled"})
        raise HTTPException(status_code=503, detail="La sélection n’a pas abouti. Lance une nouvelle sélection.") from None
    now = datetime.now(timezone.utc)
    await store.update_recommendation_session(session.id, {
        "status": "completed", "completed_at": now, "session_preferences": {**preferences, "results": results},
    })
    for item in results[:6]:
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=current.user["id"], session_id=session.id,
            event_type="shown", value=str(item["tmdb_id"]), created_at=now,
        ))
    return _guided_response(session.id, results=results)


def _question_from_candidates(candidates: list[RecommendationCandidate]) -> dict[str, Any] | None:
    options = sorted((item for item in candidates if item.score >= 0), key=lambda item: item.score, reverse=True)[:2]
    if not options:
        return None
    if len(options) == 1:
        return {"type": "single", "prompt": "Voici une piste pour toi.", "options": [_serialize_recommendation(options[0])]}
    return {
        "type": "compare",
        "prompt": "Tu préfères lequel ?",
        "options": [_serialize_recommendation(item) for item in options],
    }


def _adaptive_question_from_candidates(
    candidates: list[RecommendationCandidate],
    session_preferences: dict[str, Any],
) -> dict[str, Any] | None:
    profile = build_taste_profile([], [], [], [], datetime.now(timezone.utc))
    return build_adaptive_question(candidates, profile, session_preferences)


async def _remember_question_options(
    session: RecommendationSession,
    question: dict[str, Any],
    store: MediaStore,
) -> None:
    options = question.get("options") or []
    shown_ids = list(session.session_preferences.get("shown_tmdb_ids", []))
    shown_ids.extend(str(option["tmdb_id"]) for option in options if option.get("tmdb_id") is not None)
    session.session_preferences["shown_tmdb_ids"] = list(dict.fromkeys(shown_ids))[-20:]
    await store.update_recommendation_session(session.id, {
        "session_preferences": session.session_preferences,
    })
    now = datetime.now(timezone.utc)
    for option in options:
        tmdb_id = option.get("tmdb_id")
        if tmdb_id is None:
            continue
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=session.backstage_user_id,
            session_id=session.id, event_type="shown", value=str(tmdb_id), created_at=now,
        ))


@router.post("/recommendations/events")
async def record_recommendation_event(
    payload: RecommendationEventRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    event = RecommendationEvent(
        id=str(uuid.uuid4()),
        backstage_user_id=current.user["id"],
        session_id=payload.session_id,
        media_id=payload.media_id,
        event_type=payload.event_type,
        value=payload.value,
        numeric_value=payload.numeric_value,
        created_at=datetime.now(timezone.utc),
    )
    recorded = await store.record_recommendation_event(event)
    if payload.event_type == "already_seen":
        await _log_already_seen(store, current.user["id"], payload.value)
    return recorded.model_dump(mode="json")


@router.post("/recommendations/sessions")
async def start_recommendation_session(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
    *,
    guided: bool = False,
):
    quota = _recommendation_quota(current, store, datetime.now(timezone.utc))
    if not quota["unlimited"] and quota["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail=f"Limite quotidienne atteinte : {quota['limit']} sélections par jour.",
        )
    session = RecommendationSession(
        id=str(uuid.uuid4()),
        backstage_user_id=current.user["id"],
        created_at=datetime.now(timezone.utc),
    )
    if guided:
        session.session_preferences.update({"mode": "guided", "answers": []})
        await _reserve_recommendation_session(session, store, quota)
        return {
            **_guided_response(session.id, question=guided_question(session.session_preferences, 0)),
            "session": session.model_dump(mode="json"),
            "quota": quota,
        }
    profile, events = await _recommendation_profile(current, store)
    recent_axes = _recent_question_axes(events)
    recent_plans = _recent_question_plans(events)
    session.session_preferences.update({
        "answers": [],
        "question_index": 0,
    })
    candidates = await _recommendation_pool(current, store, session.session_preferences)
    if not candidates or not any(item.score >= 0 for item in candidates):
        return {"session": session.model_dump(mode="json"), "state": "empty", "question": None, "result": None, "quota": quota}
    gateway = _gemini_gateway()
    question_plan: list[str] = []
    if gateway.enabled:
        try:
            plan = gateway.plan_questions(profile.model_dump(mode="json"), recent_axes, recent_plans)
            question_plan = plan.axes if plan else []
            if plan and plan.usage:
                await _record_gemini_usage(store, current, session.id, plan.usage)
        except Exception as error:
            await _record_gemini_failure(store, current, session.id, error)
    session.session_preferences.update({
        "question_plan": _vary_question_plan(question_plan, recent_plans, recent_axes),
    })
    question_plan = session.session_preferences["question_plan"]
    question = _planned_question(session, candidates, profile, 0)
    if question is None:
        return {"session": session.model_dump(mode="json"), "state": "empty", "question": None, "result": None, "quota": quota}
    await _reserve_recommendation_session(session, store, quota)
    for index, axis in enumerate(question_plan):
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=current.user["id"],
            session_id=session.id, event_type="question_answered", value=f"plan:{index}:{axis}",
            created_at=datetime.now(timezone.utc),
        ))
    await _remember_question_options(session, question, store)
    return {"session": session.model_dump(mode="json"), "state": "question", "question": question, "result": None, "quota": quota}


async def _reserve_recommendation_session(
    session: RecommendationSession, store: MediaStore, quota: dict[str, Any],
) -> None:
    if quota["unlimited"]:
        await store.create_recommendation_session(session)
        return
    reserved = await store.create_recommendation_session_if_available(
        session, quota["limit"], _recommendation_day_start(datetime.now(timezone.utc)),
    )
    if reserved is None:
        raise HTTPException(
            status_code=429,
            detail=f"Limite quotidienne atteinte : {quota['limit']} sélections par jour.",
        )
    quota["used"] += 1
    quota["remaining"] = max(0, quota["limit"] - quota["used"])


@router.post("/recommendations/sessions/{session_id}/answers")
async def answer_recommendation(
    session_id: str,
    payload: RecommendationAnswerRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    session = await store.get_recommendation_session(session_id)
    if not session or session.backstage_user_id != current.user["id"]:
        raise HTTPException(status_code=404, detail="Session de recommandation introuvable")
    if session.session_preferences.get("mode") == "guided":
        return await _answer_guided_recommendation(session, payload, current, store)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Cette session est déjà terminée")
    if session.question_count >= 5:
        raise HTTPException(status_code=422, detail="Le nombre maximal de questions est atteint")
    preferences = dict(session.session_preferences)
    current_axis = str(preferences.get("current_question_axis") or "")
    current_index = int(preferences.get("question_index", session.question_count))
    if payload.answer in {"light", "intense"}:
        preferences["mood"] = payload.answer
    if payload.answer.startswith("genre:"):
        preferences["genre"] = payload.answer.removeprefix("genre:")
    if payload.answer.startswith("era:"):
        era_choice = payload.answer.removeprefix("era:")
        if era_choice in {"recent", "classic"}:
            preferences["era"] = era_choice
    if current_axis == "movie_compare" and payload.answer == "picked" and payload.value:
        try:
            picked_tmdb_id = int(payload.value)
        except ValueError:
            picked_tmdb_id = None
        if picked_tmdb_id is not None:
            choice = _resolve_compare_choice(preferences.get("compare_pair"), picked_tmdb_id)
            if choice:
                record_compare_choice(preferences, *choice)
    if payload.value:
        preferred = list(preferences.get("preferred_tmdb_ids", []))
        try:
            preferred.append(int(payload.value))
        except ValueError:
            pass
        preferences["preferred_tmdb_ids"] = preferred[-10:]
    answers = list(preferences.get("answers", []))
    answers.append({
        "axis": current_axis,
        "answer": payload.answer,
        "value": payload.value,
    })
    preferences["answers"] = answers
    preferences["question_index"] = current_index + 1
    question_count = session.question_count + 1
    if not await store.advance_recommendation_session(session_id, session.question_count, preferences):
        raise HTTPException(status_code=409, detail="Cette réponse a déjà été traitée")
    session.session_preferences = preferences
    feedback_event_type = {
        "skipped": "skipped", "not_now": "not_now", "less_like_this": "less_like_this",
        "already_seen": "already_seen",
    }.get(payload.answer, "question_answered")
    await store.record_recommendation_event(RecommendationEvent(
        id=str(uuid.uuid4()), backstage_user_id=current.user["id"],
        session_id=session_id, media_id=payload.media_id,
        event_type=feedback_event_type, value=payload.value or payload.answer,
        created_at=datetime.now(timezone.utc),
    ))
    if feedback_event_type == "already_seen":
        await _log_already_seen(store, current.user["id"], payload.value)
    if current_axis:
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=current.user["id"],
            session_id=session_id, event_type="question_answered", value=f"axis:{current_axis}",
            created_at=datetime.now(timezone.utc),
        ))
    candidates = await _recommendation_pool(current, store, preferences)
    session.session_preferences = preferences
    profile, _ = await _recommendation_profile(current, store)
    question = None if payload.answer == "surprise" else _planned_question(session, candidates, profile, current_index + 1)
    if question is None:
        result = None
        gateway = _gemini_gateway()
        if gateway.enabled and candidates:
            try:
                selection = gateway.select_final(
                    {"taste_profile": profile.model_dump(mode="json"), "session_preferences": preferences},
                    answers,
                    [item.model_dump(mode="json") for item in candidates if item.score >= 0],
                )
                if selection:
                    result = next((item for item in candidates if item.tmdb_id == selection.tmdb_id), None)
                    if selection.usage:
                        await _record_gemini_usage(store, current, session_id, selection.usage)
            except Exception as error:
                await _record_gemini_failure(store, current, session_id, error)
        result = result or choose_from_top(candidates, Random(session_id), top_n=8)
        await store.update_recommendation_session(session_id, {
            "status": "completed", "completed_at": datetime.now(timezone.utc),
        })
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=current.user["id"],
            session_id=session_id, media_id=payload.media_id,
            event_type="session_completed", value=str(result.tmdb_id) if result else None,
            created_at=datetime.now(timezone.utc),
        ))
        return {"session_id": session_id, "state": "result", "question": None, "result": _serialize_recommendation(result)}
    await _remember_question_options(session, question, store)
    return {"session_id": session_id, "state": "question", "question": question, "result": None}


async def _find_or_create_movie(store: MediaStore, tmdb_id: int) -> Media:
    media = next((item for item in await store.fetch_all() if item.type == "Film" and item.tmdb_id == tmdb_id), None)
    if media is not None:
        return media
    tmdb = TMDBClient()
    details = await tmdb.get_movie_details(tmdb_id)
    if not details:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB")
    return await store.create({
        "title": details.get("title") or details.get("original_title") or "Sans titre",
        "original_title": details.get("original_title") or None,
        "type": "Film", "status": "À regarder", "rating": None,
        "release_date": details.get("release_date") or None,
        "director": tmdb.get_director(details), "categories": tmdb.get_genres(details),
        "synopsis": (details.get("overview") or "")[:2000],
        "cover_url": tmdb.get_poster_url(details), "backdrop_url": tmdb.get_backdrop_url(details),
        "cast": tmdb.get_cast(details, limit=5), "tmdb_ok": True, "tmdb_id": tmdb_id,
    })


@router.post("/recommendations/sessions/{session_id}/confirm")
async def confirm_recommendation(
    session_id: str,
    payload: RecommendationConfirmRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
    service: MediaServerService = Depends(get_media_server_service),
):
    session = await store.get_recommendation_session(session_id)
    if not session or session.backstage_user_id != current.user["id"]:
        raise HTTPException(status_code=404, detail="Session de recommandation introuvable")
    if session.session_preferences.get("mode") == "guided":
        candidate = next((
            item for item in session.session_preferences.get("results", [])
            if item["tmdb_id"] == payload.tmdb_id
        ), None)
        if session.status != "completed" or not candidate or candidate["action"] not in {"request", "rent"}:
            raise HTTPException(status_code=403, detail="Ce film ne peut pas être demandé depuis cette sélection")
        if not payload.download:
            raise HTTPException(status_code=422, detail="La demande de film doit être confirmée")
        if candidate["action"] == "rent":
            media = await _find_or_create_movie(store, payload.tmdb_id)
            acquired = await _acquire_media(media, AcquisitionRequest(), current, service)
        else:
            acquired = await create_seerr_request(
                SeerrRequestCreate(tmdb_id=payload.tmdb_id, media_type="movie"), current, service,
            )
        available = acquired.get("availability")
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=current.user["id"], session_id=session_id,
            media_id=available.media_id if available else None, event_type="confirmed",
            value=str(payload.tmdb_id), created_at=datetime.now(timezone.utc),
        ))
        # Reuse the playback access check when a rental has just opened.
        if available and available.jellyfin_id:
            await _ensure_playback_access(current, available.media_id, store)
            return {**acquired, "action": "play", "media_id": available.media_id}
        return {**acquired, "action": "pending"}
    events = await store.list_recommendation_events(current.user["id"])
    selected = any(
        event.session_id == session_id
        and event.event_type == "session_completed"
        and str(event.value) == str(payload.tmdb_id)
        for event in events
    )
    if not selected:
        raise HTTPException(status_code=403, detail="Ce film ne correspond pas à la recommandation validée")

    media = await _find_or_create_movie(store, payload.tmdb_id)

    availability = await store.get_availability(media.id)
    download_error = None
    if payload.download and current.user.get("role") != "admin":
        # A flatmate's pick is a temporary rental, validated later by the admin.
        try:
            acquired = await _acquire_media(media, AcquisitionRequest(), current, service)
            availability = acquired["availability"]
        except HTTPException as error:
            download_error = str(error.detail)
        except (MediaServerError, RuntimeError, ValueError) as error:
            download_error = str(error)
    elif payload.download and not availability:
        try:
            availability = await service.add_with_defaults(media)
        except (MediaServerError, RuntimeError, ValueError) as error:
            download_error = str(error)
    await store.record_recommendation_event(RecommendationEvent(
        id=str(uuid.uuid4()), backstage_user_id=current.user["id"], session_id=session_id,
        media_id=media.id, event_type="confirmed", value=str(payload.tmdb_id),
        created_at=datetime.now(timezone.utc),
    ))
    return {
        "media": media.model_dump(mode="json"),
        "availability": availability.model_dump(mode="json") if availability else None,
        "download_error": download_error,
    }


@router.post("/recommendations/sessions/{session_id}/finish")
async def finish_recommendation(
    session_id: str,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    session = await store.get_recommendation_session(session_id)
    if not session or session.backstage_user_id != current.user["id"]:
        raise HTTPException(status_code=404, detail="Session de recommandation introuvable")
    updated = await store.update_recommendation_session(session_id, {
        "status": "completed", "completed_at": datetime.now(timezone.utc),
    })
    return updated.model_dump(mode="json")


def _optional_tmdb_client() -> Optional[TMDBClient]:
    """TMDB client, or None when no API key is configured."""
    try:
        return TMDBClient()
    except ValueError:
        return None


@router.get("/medias/{media_id}/episodes")
async def get_series_episodes(
    media_id: str,
    store: MediaStore = Depends(get_store),
    current: AuthContext = Depends(get_current_user),
    jellyfin: Optional[JellyfinClient] = Depends(get_jellyfin_client),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    # Series created by the library sync have no episode yet, and older series
    # lack air dates/runtimes/seasons: load them from TMDB (weekly at most).
    await ensure_series_metadata(store, _optional_tmdb_client(), media)

    user_id = current.user["id"] if isinstance(current, AuthContext) else None
    if user_id:
        episodes = await store.list_episodes_for_user(media_id, user_id)
        progress = await store.series_progress_for_user(media_id, user_id)
        playback = await store.list_episode_playback(media_id, user_id)
    else:
        episodes = await store.list_episodes(media_id)
        progress = await store.series_progress(media_id)
        playback = {}
    availability = await store.get_availability(media_id)
    playable_episodes: set[tuple[int, int]] = set()
    has_server = False
    list_series_episodes = getattr(jellyfin, "list_series_episodes", None)
    if availability and availability.jellyfin_id and callable(list_series_episodes):
        try:
            remote_episodes = await list_series_episodes(availability.jellyfin_id)
            playable_episodes = {
                (item["ParentIndexNumber"], item["IndexNumber"])
                for item in remote_episodes
            }
            has_server = True
        except (httpx.HTTPError, ValueError):
            logger.exception("[jellyfin-episodes] Impossible de vérifier les épisodes de %s", media_id)
    episodes = [
        {
            **episode,
            "available": (episode["season_number"], episode["episode_number"]) in playable_episodes,
        }
        for episode in episodes
    ]
    view = build_series_view(
        episodes, await store.get_series_metadata(media_id), playback, has_server=has_server,
    )
    return {**view, "progress": progress, "has_server": has_server}


class UpdateSeasonRequest(BaseModel):
    watched: bool


@router.patch("/medias/{media_id}/seasons/{season_number}/watched")
async def update_season_watched(
    media_id: str,
    season_number: int,
    payload: UpdateSeasonRequest,
    store: MediaStore = Depends(get_store),
    current: AuthContext = Depends(get_current_user),
    jellyfin: Optional[JellyfinClient] = Depends(get_jellyfin_client),
):
    """Mark every episode of a season as watched or unwatched in one call."""
    media = await store.fetch_one(media_id)
    if not media or media.type != "Série":
        raise HTTPException(status_code=404, detail="Série non trouvée")
    if isinstance(current, AuthContext):
        changed = await store.set_user_season_watched(media_id, season_number, current.user["id"], payload.watched)
    else:
        episodes = [e for e in await store.list_episodes(media_id) if e["season_number"] == season_number]
        for episode in episodes:
            await store.set_episode_watched(episode["id"], payload.watched)
        changed = len(episodes)
    if not changed:
        raise HTTPException(status_code=404, detail="Saison non trouvée")
    return await get_series_episodes(media_id, store, current, jellyfin)


@router.patch("/episodes/{episode_id}")
async def update_episode(
    episode_id: str,
    payload: UpdateEpisodeRequest,
    store: MediaStore = Depends(get_store),
    current: AuthContext = Depends(get_current_user),
):
    if isinstance(current, AuthContext):
        episode = await store.set_user_episode_watched(episode_id, current.user["id"], payload.watched)
        progress = await store.series_progress_for_user(episode["media_id"], current.user["id"]) if episode else None
    else:
        episode = await store.set_episode_watched(episode_id, payload.watched)
        progress = await store.series_progress(episode["media_id"]) if episode else None
    if not episode:
        raise HTTPException(status_code=404, detail="Épisode non trouvé")

    return {
        "episode": episode,
        "progress": progress,
    }


@router.post("/medias/from_tmdb", response_model=Media, dependencies=[Depends(require_admin)])
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
        "original_title": details.get("original_title") or None,
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
        "tmdb_id": payload.tmdb_id,
    })


async def create_series_from_tmdb(
    payload: CreateFromTMDBRequest,
    store: MediaStore,
    tmdb: TMDBClient,
) -> Media:
    details = await tmdb.get_tv_details(payload.tmdb_id)
    if not details:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB")

    tmdb_series = await _fetch_tmdb_series(payload.tmdb_id, details, tmdb)

    series = await store.create({
        "title": details.get("name") or details.get("title") or details.get("original_name") or "Sans titre",
        "original_title": details.get("original_name") or None,
        "type": "Série",
        "status": "À regarder",
        "rating": None,
        "release_date": details.get("first_air_date") or details.get("release_date") or None,
        "director": tmdb.get_director(details),
        "categories": tmdb.get_genres(details),
        "synopsis": (details.get("overview") or "")[:2000],
        "cover_url": tmdb.get_poster_url(details),
        "backdrop_url": tmdb.get_backdrop_url(details),
        "cast": tmdb.get_cast(details, limit=5),
        "tmdb_ok": True,
        "tmdb_id": payload.tmdb_id,
    })
    await store.create_episodes(series.id, tmdb_series["episodes"])
    await store.save_series_metadata(series.id, tmdb_series["seasons"], tmdb_series["info"])
    return await store.fetch_one(series.id)


async def _fetch_tmdb_series(
    tmdb_id: int, details: Dict[str, Any], tmdb: TMDBClient,
) -> Dict[str, Any]:
    """Load episodes, seasons and series facts for an import or refresh."""
    series = await fetch_tmdb_series(tmdb, tmdb_id, details)
    if series is None:
        raise HTTPException(status_code=502, detail="Impossible de récupérer les épisodes TMDB")
    return series


async def refresh_series_from_tmdb(media_id: str, store: MediaStore, tmdb: TMDBClient) -> Media:
    """Refresh a linked series while retaining local watched episode state."""
    series = await store.fetch_one(media_id)
    if not series:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    if series.type != "Série":
        raise HTTPException(status_code=400, detail="Ce média n'est pas une série")
    tmdb_id = series.tmdb_id
    if not tmdb_id:
        # Les séries importées avant l'ajout de tmdb_id restent enrichissables :
        # on les associe une première fois à partir de leur titre local.
        matches = await tmdb.search_tv(series.title)
        if not matches or not matches[0].get("id"):
            raise HTTPException(status_code=404, detail="Aucune série TMDB trouvée pour ce titre")
        tmdb_id = int(matches[0]["id"])

    details = await tmdb.get_tv_details(tmdb_id)
    if not details:
        raise HTTPException(status_code=502, detail="Impossible de récupérer les détails TMDB")
    tmdb_series = await _fetch_tmdb_series(tmdb_id, details, tmdb)
    updates = {
        "original_title": details.get("original_name") or series.original_title,
        "release_date": details.get("first_air_date") or details.get("release_date") or series.release_date,
        "director": tmdb.get_director(details) or series.director,
        "categories": tmdb.get_genres(details) or series.categories,
        "synopsis": (details.get("overview") or series.synopsis or "")[:2000],
        "cover_url": tmdb.get_poster_url(details) or series.cover_url,
        "backdrop_url": tmdb.get_backdrop_url(details) or series.backdrop_url,
        "cast": tmdb.get_cast(details, limit=5) or series.cast,
        "tmdb_ok": True,
        "tmdb_id": tmdb_id,
    }
    await store.update(media_id, updates)
    await save_tmdb_series(store, media_id, tmdb_series)
    return await store.fetch_one(media_id)


@router.post("/series/from_tmdb", response_model=Media, dependencies=[Depends(require_admin)])
async def create_series_from_tmdb_endpoint(
    payload: CreateFromTMDBRequest,
    store: MediaStore = Depends(get_store),
):
    return await create_series_from_tmdb(payload, store, TMDBClient())


@router.post("/series/{media_id}/refresh", response_model=Media, dependencies=[Depends(require_admin)])
async def refresh_series_from_tmdb_endpoint(
    media_id: str,
    store: MediaStore = Depends(get_store),
):
    return await refresh_series_from_tmdb(media_id, store, TMDBClient())


@router.patch("/medias/{media_id}", response_model=Media, dependencies=[Depends(require_admin)])
async def update_media(
    media_id: str,
    payload: UpdateMediaRequest,
    store: MediaStore = Depends(get_store),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    update_fields: Dict[str, Any] = {}
    if payload.title is not None:
        update_fields["title"] = payload.title
    if payload.original_title is not None:
        update_fields["original_title"] = payload.original_title
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
    if payload.rating is not None and str(payload.rating).strip():
        update_fields["status"] = "Terminé"
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


@router.delete("/medias/{media_id}", dependencies=[Depends(require_admin)])
async def delete_media(
    media_id: str,
    delete_files: bool = False,
    service: MediaServerService = Depends(get_media_server_service),
):
    """Remove a fiche from the catalogue, optionally with its Radarr files."""
    store = service.store
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    files_deleted = False
    if delete_files:
        availability = await store.get_availability(media_id)
        if availability and availability.provider == "radarr" and availability.arr_id:
            if service.radarr is None:
                raise HTTPException(status_code=503, detail="Radarr n'est pas configuré")
            try:
                await service.radarr.delete_movie(availability.arr_id, delete_files=True)
            except (MediaServerError, RuntimeError) as error:
                raise HTTPException(
                    status_code=502, detail=f"Radarr n'a pas pu supprimer les fichiers : {error}",
                ) from error
            files_deleted = True

    await store.delete(media_id)
    return {"deleted": True, "media_id": media_id, "title": media.title, "files_deleted": files_deleted}



@router.get("/media-server/status")
async def media_server_status():
    return {
        "radarr": {"configured": Config.radarr_enabled()},
        "sonarr": {"configured": Config.sonarr_enabled()},
        "seerr": {"configured": Config.seerr_enabled()},
        "jellyfin": {"configured": Config.jellyfin_enabled()},
    }


_PLAYBACK_HEALTH_TTL_SEC = 30
_playback_health_cache: dict[str, Any] = {"checked_at": 0.0, "online": None}


async def playback_server_online(jellyfin: Optional[JellyfinClient] = None, *, now: Optional[float] = None) -> Optional[bool]:
    """None when no playback server is configured; cached for a few seconds."""
    if jellyfin is None:
        if not Config.jellyfin_enabled():
            return None
        jellyfin = JellyfinClient(Config.JELLYFIN_URL, Config.JELLYFIN_API_KEY)
    now = time.monotonic() if now is None else now
    cached = _playback_health_cache
    if cached["online"] is not None and now - cached["checked_at"] < _PLAYBACK_HEALTH_TTL_SEC:
        return cached["online"]
    online = await jellyfin.ping()
    cached.update(checked_at=now, online=online)
    return online


@router.get("/media-server/health")
async def media_server_health():
    online = await playback_server_online()
    return {"playback": "disabled" if online is None else "online" if online else "offline"}


_PLAYBACK_RENTAL_STATES = {"available", "keep_requested", "kept"}


async def _ensure_playback_access(
    current: AuthContext, media_id: str, store: MediaStore,
) -> Optional[Rental]:
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    if current.user.get("role") == "admin":
        return None

    now = datetime.now(timezone.utc)
    user_rentals = await store.list_user_rentals(current.user["id"])
    owned = next((rental for rental in user_rentals if rental.media_id == media_id), None)
    if owned and owned.status in _PLAYBACK_RENTAL_STATES:
        if owned.expires_at is None or owned.expires_at > now or owned.storage_policy == "permanent":
            return owned

    all_rentals = await store.list_rentals_for_media(media_id)
    if not all_rentals:
        # Administratively managed permanent media has no user rental row.
        return None
    if any(rental.status == "kept" or rental.storage_policy == "permanent" for rental in all_rentals):
        # A rental the admin decided to keep joins the shared library.
        return None
    raise HTTPException(status_code=403, detail="Tu n'as pas accès à ce contenu")


@router.get("/medias/{media_id}/availability")
async def get_availability(
    media_id: str,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    await _ensure_playback_access(current, media_id, service.store)
    await service.sync_media(media_id)
    availability = await service.store.get_availability(media_id)
    playback_url = await service.playback_url(media_id)
    return {"availability": availability, "playback_url": playback_url}


@router.get("/medias/{media_id}/playback/manifest")
async def get_playback_manifest(
    media_id: str,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    audio_stream_index: Optional[int] = None,
    subtitle_stream_index: Optional[int] = None,
    start_time_ticks: Optional[int] = None,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    if (season_number is None) != (episode_number is None):
        raise HTTPException(status_code=422, detail="Saison et épisode requis")
    await _ensure_playback_access(current, media_id, service.store)
    playback = await service.playback_manifest(media_id, season_number, episode_number)
    if not playback or not service.jellyfin:
        raise HTTPException(status_code=404, detail="Lecture indisponible")
    try:
        options = await service.playback_options(media_id, season_number, episode_number)
        if not options:
            raise HTTPException(status_code=404, detail="Source Jellyfin indisponible")
        response = await service.jellyfin.fetch_playback_resource(
            playback["item_id"], "master.m3u8",
            service.jellyfin.playback_manifest_params(
                playback["item_id"],
                media_source_id=options["media_source_id"],
                audio_stream_index=audio_stream_index,
                subtitle_stream_index=subtitle_stream_index,
                start_time_ticks=start_time_ticks,
            ),
        )
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as error:
        logger.exception("[jellyfin-playback] Manifest failed for %s S%sE%s", media_id, season_number, episode_number)
        status = getattr(getattr(error, "response", None), "status_code", None)
        raise HTTPException(status_code=502, detail=f"Flux Jellyfin indisponible{f' (HTTP {status})' if status else ''}") from None
    manifest = _rewrite_hls_manifest(response.text, media_id, season_number, episode_number)
    return Response(content=manifest, media_type="application/vnd.apple.mpegurl")


@router.get("/medias/{media_id}/playback/options")
async def get_playback_options(
    media_id: str,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    if (season_number is None) != (episode_number is None):
        raise HTTPException(status_code=422, detail="Saison et épisode requis")
    await _ensure_playback_access(current, media_id, service.store)
    try:
        options = await service.playback_options(media_id, season_number, episode_number)
    except (httpx.HTTPError, ValueError) as error:
        logger.exception("[jellyfin-playback] Track lookup failed for %s S%sE%s", media_id, season_number, episode_number)
        status = getattr(getattr(error, "response", None), "status_code", None)
        raise HTTPException(status_code=502, detail=f"Pistes Jellyfin indisponibles{f' (HTTP {status})' if status else ''}") from None
    if not options:
        raise HTTPException(status_code=404, detail="Lecture indisponible")
    return options


async def _get_jellyfin_playback_target(
    media_id: str,
    request: Request,
    season_number: Optional[int],
    episode_number: Optional[int],
    current: AuthContext,
    service: MediaServerService,
) -> dict[str, str]:
    if (season_number is None) != (episode_number is None):
        raise HTTPException(status_code=422, detail="Saison et épisode requis")
    await _ensure_playback_access(current, media_id, service.store)
    if not service.jellyfin:
        raise HTTPException(status_code=503, detail="Jellyfin n'est pas configuré")
    playback = await service.playback_manifest(media_id, season_number, episode_number)
    if not playback:
        raise HTTPException(status_code=404, detail="Lecture indisponible")

    public_url = Config.JELLYFIN_PUBLIC_URL
    if not public_url:
        # JELLYFIN_URL may be a Docker-only hostname. Build the browser URL from
        # Backstage's public host and Jellyfin's published port instead.
        origin = urlsplit(str(request.base_url))
        hostname = origin.hostname or "localhost"
        netloc = f"[{hostname}]:8096" if ":" in hostname else f"{hostname}:8096"
        public_url = urlunsplit((origin.scheme, netloc, "", "", ""))
    return {
        "url": service.jellyfin.playback_url(playback["item_id"], base_url=public_url),
        "item_id": playback["item_id"],
    }


@router.get("/medias/{media_id}/playback/jellyfin-url")
async def get_jellyfin_player_url(
    media_id: str,
    request: Request,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    target = await _get_jellyfin_playback_target(
        media_id, request, season_number, episode_number, current, service,
    )
    return RedirectResponse(target["url"], status_code=307)


@router.get("/medias/{media_id}/playback/jellyfin-target")
async def get_jellyfin_playback_target(
    media_id: str,
    request: Request,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    return await _get_jellyfin_playback_target(
        media_id, request, season_number, episode_number, current, service,
    )


@router.get("/medias/{media_id}/playback/resource/{resource_path:path}")
async def get_playback_resource(
    media_id: str,
    resource_path: str,
    request: Request,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    await _ensure_playback_access(current, media_id, service.store)
    query = {key: value for key, value in request.query_params.multi_items() if key.lower() != "api_key"}
    try:
        season_number = int(query.pop("season_number")) if "season_number" in query else None
        episode_number = int(query.pop("episode_number")) if "episode_number" in query else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Saison ou épisode invalide") from None
    if (season_number is None) != (episode_number is None):
        raise HTTPException(status_code=422, detail="Saison et épisode requis")
    try:
        response = await service.playback_resource(
            media_id, resource_path, query, season_number, episode_number,
        )
    except (httpx.HTTPError, ValueError) as error:
        logger.exception("[jellyfin-playback] Resource failed for %s: %s", media_id, resource_path)
        status = getattr(getattr(error, "response", None), "status_code", None)
        raise HTTPException(status_code=502, detail=f"Ressource Jellyfin indisponible{f' (HTTP {status})' if status else ''}") from None
    if response is None:
        raise HTTPException(status_code=404, detail="Lecture indisponible")
    media_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
    return Response(content=response.content, media_type=media_type, headers={
        key: value for key, value in response.headers.items()
        if key.lower() in {"content-length", "content-range", "accept-ranges", "cache-control"}
    })


@router.post("/medias/{media_id}/acquisition")
async def request_acquisition(
    media_id: str,
    payload: AcquisitionRequest,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    media = await service.store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    return await _acquire_media(media, payload, current, service)


async def _acquire_media(
    media: Media, payload: AcquisitionRequest, current: AuthContext, service: MediaServerService,
) -> dict[str, Any]:
    """Download a media: permanent for the admin, a temporary rental for everyone else."""
    media_id = media.id
    if not media.tmdb_id:
        raise HTTPException(status_code=409, detail="Associe d'abord ce film à TMDB")
    is_admin = current.user.get("role") == "admin"
    owner_id = current.user["id"]
    if media.type == "Série" and (payload.seasons or payload.episodes):
        return await _acquire_series_parts(media, payload, current, service)
    if not is_admin and media.type == "Série":
        raise HTTPException(status_code=403, detail="Choisis une saison à louer")
    if not is_admin:
        now = datetime.now(timezone.utc)
        await service.store.expire_rentals(now)
        existing_rental = await service.store.find_active_rental(owner_id, media_id)
        if existing_rental:
            return {
                "availability": await service.store.get_availability(media_id),
                "rental": _serialize_rental(existing_rental),
            }
        availability = await service.store.get_availability(media_id)
        if availability and availability.state == "available":
            media_rentals = await service.store.list_rentals_for_media(media_id)
            if not media_rentals or any(
                rental.status == "kept" or rental.storage_policy == "permanent" for rental in media_rentals
            ):
                # Already in the shared library: nothing to download, nothing to rent.
                return {"availability": availability}
        slots = await service.store.count_rental_slots(owner_id)
        if availability and availability.state == "available":
            if slots["in_use"] >= MAX_ACTIVE_RENTALS:
                raise HTTPException(
                    status_code=409,
                    detail=f"Limite de {MAX_ACTIVE_RENTALS} locations en cours atteinte",
                )
        elif slots["queued"] >= MAX_QUEUED_RENTALS:
            raise HTTPException(
                status_code=409,
                detail=f"File d'attente pleine : {MAX_QUEUED_RENTALS} films attendent déjà une source",
            )
        if availability and availability.state == "available":
            # The file is already on disk for another flatmate's rental: share it.
            rental = await service.store.create_rental(Rental(
                id=str(uuid.uuid4()), media_id=media_id, backstage_user_id=owner_id,
                status="available", rental_scope="series" if media.type == "Série" else "movie",
                requested_at=now, available_at=now, expires_at=now + timedelta(days=21),
                created_at=now, updated_at=now,
            ))
            return {"availability": availability, "rental": _serialize_rental(rental)}
    existing = await service.store.get_availability(media_id)
    if existing and (existing.state in IN_PROGRESS_STATES or existing.jellyfin_id):
        # Already on Jellyfin, or a request/download exists: show its state, no duplicate.
        response: dict[str, Any] = {"availability": existing, "already_requested": True}
        if not is_admin:
            now = datetime.now(timezone.utc)
            rental = await service.store.create_rental(Rental(
                id=str(uuid.uuid4()), media_id=media_id, backstage_user_id=owner_id,
                status=_rental_status_for(existing.state),
                rental_scope="series" if media.type == "Série" else "movie",
                requested_at=now, created_at=now, updated_at=now,
            ))
            response["rental"] = _serialize_rental(rental)
        return response
    if not is_admin and media.type == "Film" and hasattr(service, "acquisition_defaults"):
        defaults = await service.acquisition_defaults(media)
        default_profile_id = defaults.get("quality_profile_id")
        if default_profile_id is not None and payload.quality_profile_id not in {None, default_profile_id}:
            raise HTTPException(
                status_code=422,
                detail=f"Les utilisateurs non-admin doivent utiliser le profil {Config.RADARR_DEFAULT_QUALITY_PROFILE_NAME}",
            )
        payload = payload.model_copy(update={
            "quality_profile_id": payload.quality_profile_id or default_profile_id,
            "root_folder": defaults.get("root_folder"),
        })
    if not is_admin:
        if hasattr(service, "storage_status"):
            storage = await service.storage_status()
            if storage.get("low_space") or (
                storage.get("min_free_bytes") is not None
                and storage["min_free_bytes"] < Config.min_free_bytes()
            ):
                raise HTTPException(status_code=507, detail="Espace disque insuffisant pour une nouvelle location")
            if storage.get("temporary_quota_reached") or (
                storage.get("temporary_bytes", 0) >= Config.temporary_max_bytes()
            ):
                raise HTTPException(status_code=507, detail="Quota de stockage temporaire atteint")
    try:
        availability = await service.add(
            media, payload.quality_profile_id, payload.root_folder,
            payload.language_profile_id, payload.monitor,
        )
        response = {"availability": availability}
        if not is_admin:
            now = datetime.now(timezone.utc)
            rental = await service.store.create_rental(Rental(
                id=str(uuid.uuid4()), media_id=media_id, backstage_user_id=owner_id,
                status=_rental_status_for(availability.state),
                rental_scope="series" if media.type == "Série" else "movie",
                requested_at=now, created_at=now, updated_at=now,
            ))
            response["rental"] = _serialize_rental(rental)
        return response
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MediaServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error) or "Service non configuré") from error


async def _acquire_series_parts(
    media: Media, payload: AcquisitionRequest, current: AuthContext, service: MediaServerService,
) -> dict[str, Any]:
    """Download chosen seasons/episodes: the admin keeps them, a flatmate rents one season."""
    is_admin = current.user.get("role") == "admin"
    owner_id = current.user["id"]
    seasons = sorted({number for number in payload.seasons or [] if number > 0})
    episodes = sorted({(ref.season_number, ref.episode_number) for ref in payload.episodes or []})
    if not seasons and not episodes:
        raise HTTPException(status_code=422, detail="Aucune saison ni aucun épisode demandé")
    rental_season: Optional[int] = None
    if not is_admin:
        if episodes or len(seasons) != 1:
            raise HTTPException(status_code=403, detail="Tu peux louer une saison à la fois")
        rental_season = seasons[0]
        now = datetime.now(timezone.utc)
        await service.store.expire_rentals(now)
        existing_rental = await service.store.find_active_rental(owner_id, media.id, rental_season)
        if existing_rental:
            return {
                "availability": await service.store.get_availability(media.id),
                "rental": _serialize_rental(existing_rental),
            }
        availability = await service.store.get_availability(media.id)
        if availability and availability.jellyfin_id:
            try:
                on_server = await service.seasons_on_server(media, availability.jellyfin_id)
            except (httpx.HTTPError, ValueError):
                on_server = set()
            if rental_season in on_server:
                # Already complete in the shared library: nothing to rent.
                return {"availability": availability, "season_available": True}
        slots = await service.store.count_rental_slots(owner_id)
        if slots["queued"] >= MAX_QUEUED_RENTALS:
            raise HTTPException(
                status_code=409,
                detail=f"File d'attente pleine : {MAX_QUEUED_RENTALS} demandes attendent déjà une source",
            )
        if hasattr(service, "storage_status"):
            storage = await service.storage_status()
            if storage.get("low_space") or storage.get("temporary_quota_reached"):
                raise HTTPException(status_code=507, detail="Espace disque insuffisant pour une nouvelle location")
    try:
        availability = await service.add(
            media, payload.quality_profile_id, payload.root_folder, payload.language_profile_id,
            payload.monitor, seasons=seasons or None, episodes=episodes or None,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MediaServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error) or "Service non configuré") from error
    response: dict[str, Any] = {"availability": availability, "seasons": seasons, "episodes": episodes}
    if rental_season is not None:
        now = datetime.now(timezone.utc)
        rental = await service.store.create_rental(Rental(
            id=str(uuid.uuid4()), media_id=media.id, backstage_user_id=owner_id,
            status="requested", rental_scope="season", season_number=rental_season,
            requested_at=now, created_at=now, updated_at=now,
        ))
        response["rental"] = _serialize_rental(rental)
    return response


@router.get("/rentals")
async def list_rentals(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    limits = {"max_active_rentals": MAX_ACTIVE_RENTALS, "max_queued_rentals": MAX_QUEUED_RENTALS}
    if current.user.get("role") == "admin":
        return {"rentals": [], **limits}
    await store.expire_rentals(datetime.now(timezone.utc))
    rentals = await store.list_user_rentals(current.user["id"])
    states = {item.media_id: item.state for item in await store.list_availabilities()}
    return {
        "rentals": [
            {**_serialize_rental(rental), "download_state": states.get(rental.media_id)}
            for rental in rentals
        ],
        **limits,
    }


def _is_waiting_for_source(rental: Rental, availability: Optional[Availability]) -> bool:
    return rental.status == "requested" and (availability is None or availability.state in {"requested", "error"})


@router.post("/rentals/{rental_id}/cancel")
async def cancel_rental(
    rental_id: str,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    """Let a flatmate drop a request that is still waiting for a source."""
    store = service.store
    rental = await store.get_rental(rental_id)
    if not rental or rental.backstage_user_id != current.user["id"]:
        raise HTTPException(status_code=404, detail="Location non trouvée")
    availability = await store.get_availability(rental.media_id)
    if not _is_waiting_for_source(rental, availability):
        raise HTTPException(status_code=409, detail="Le téléchargement a déjà commencé : la location ne peut plus être annulée")
    rental = await store.update_rental(rental_id, {"status": "cancelled"})
    still_wanted = any(
        other.id != rental_id and (
            other.status in {"requested", "downloading", "available", "keep_requested", "kept"}
            or other.storage_policy == "permanent"
        )
        for other in await store.list_rentals_for_media(rental.media_id)
    )
    warning = None
    if not still_wanted and availability and availability.arr_id and getattr(service, "radarr", None) and availability.provider == "radarr":
        try:
            await service.radarr.delete_movie(availability.arr_id, delete_files=True)
            await store.upsert_availability(availability.model_copy(update={
                "arr_id": None, "jellyfin_id": None, "state": "error", "progress_percent": None,
                "last_error": "Demande annulée", "last_synced_at": datetime.now(timezone.utc),
            }))
        except RuntimeError as error:
            warning = f"Location annulée, mais Radarr n'a pas pu être nettoyé : {error}"
    return {"rental": _serialize_rental(rental), "warning": warning}


@router.post("/rentals/{rental_id}/keep")
async def request_rental_keep(
    rental_id: str,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    if current.user.get("role") == "admin":
        raise HTTPException(status_code=404, detail="Location non trouvée")
    rental = await store.get_rental(rental_id)
    if not rental or rental.backstage_user_id != current.user["id"]:
        raise HTTPException(status_code=404, detail="Location non trouvée")
    if rental.status not in {"available", "keep_requested"}:
        raise HTTPException(status_code=409, detail="Le film n'est pas encore disponible")
    if rental.status == "available":
        rental = await store.update_rental(rental_id, {
            "status": "keep_requested",
            "keep_requested_at": datetime.now(timezone.utc),
        })
    return {"rental": _serialize_rental(rental)}


@router.get("/admin/rentals/keep-requests")
async def list_keep_requests(
    _: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
    auth_store: AuthStore = Depends(get_auth_store),
):
    users = {user["id"]: user["display_name"] for user in auth_store.list_users()}
    requests = []
    for item in await store.list_keep_requested_rentals():
        rental = item["rental"]
        requests.append({
            "media_title": item["media_title"],
            "requester_name": users.get(rental["backstage_user_id"], "Compte supprimé"),
            "rental": rental,
        })
    return {"requests": requests}


@router.get("/admin/rentals")
async def list_admin_rentals(
    _: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
    auth_store: AuthStore = Depends(get_auth_store),
):
    users = {user["id"]: user["display_name"] for user in auth_store.list_users()}
    rentals = []
    for item in await store.list_admin_rentals():
        rental = item["rental"]
        rentals.append({
            "media_title": item["media_title"],
            "requester_name": users.get(rental.backstage_user_id, "Compte supprimé"),
            "rental": _serialize_rental(rental),
        })
    return {"rentals": rentals}


@router.get("/admin/rentals/cleanup-preview")
async def cleanup_preview(
    _: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
):
    return {
        "simulation": True,
        "items": await store.cleanup_preview(datetime.now(timezone.utc)),
        "message": "Simulation uniquement : aucun fichier ne sera supprimé.",
    }


async def _extension_message(store: MediaStore, rental: Rental) -> str:
    media = await store.fetch_one(rental.media_id)
    title = f"La location de « {media.title} »" if media else "Ta location"
    ends = f", jusqu'au {rental.expires_at.astimezone().strftime('%d/%m/%Y')}" if rental.expires_at else ""
    return f"{title} a été prolongée de 7 jours{ends}."


async def _apply_rental_decision(
    rental_id: str,
    decision: str,
    current: AuthContext,
    store: MediaStore,
):
    now = datetime.now(timezone.utc)
    try:
        rental = await store.decide_rental(rental_id, decision, current.user["id"], now)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not rental:
        raise HTTPException(status_code=404, detail="Location non trouvée")
    media = await store.fetch_one(rental.media_id)
    title = f"« {media.title} »" if media else "Ton film"
    if decision == "accepted":
        kind, message = "retention_accepted", f"{title} est conservé définitivement : il reste dans la bibliothèque commune."
    else:
        ends = f" Ta location se termine le {rental.expires_at.astimezone().strftime('%d/%m/%Y')}." if rental.expires_at else ""
        kind, message = "retention_refused", f"{title} ne sera pas conservé.{ends}"

    await store.create_notification(Notification(
        id=str(uuid.uuid4()), backstage_user_id=rental.backstage_user_id,
        kind=kind, message=message, created_at=now,
    ))
    return {"rental": _serialize_rental(rental)}


@router.post("/admin/rentals/{rental_id}/keep")
async def accept_keep_request(
    rental_id: str,
    current: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
):
    return await _apply_rental_decision(rental_id, "accepted", current, store)


@router.post("/admin/rentals/{rental_id}/refuse")
async def refuse_keep_request(
    rental_id: str,
    current: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
):
    return await _apply_rental_decision(rental_id, "refused", current, store)


@router.post("/admin/rentals/{rental_id}/extend")
async def extend_rental(
    rental_id: str,
    current: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
):
    now = datetime.now(timezone.utc)
    try:
        rental = await store.extend_rental(rental_id, now)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not rental:
        raise HTTPException(status_code=404, detail="Location non trouvée")
    await store.create_notification(Notification(
        id=str(uuid.uuid4()), backstage_user_id=rental.backstage_user_id,
        kind="retention_extended", message=await _extension_message(store, rental), created_at=now,
    ))
    return {"rental": _serialize_rental(rental)}


@router.post("/admin/rentals/{rental_id}/revoke")
async def revoke_rental_access(
    rental_id: str,
    current: AuthContext = Depends(require_admin),
    store: MediaStore = Depends(get_store),
    service: MediaServerService = Depends(get_media_server_service),
):
    now = datetime.now(timezone.utc)
    previous_rental = await store.get_rental(rental_id)
    was_pending = bool(previous_rental and previous_rental.status in {"requested", "downloading"})
    try:
        rental = await store.revoke_rental(rental_id, current.user["id"], now)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not rental:
        raise HTTPException(status_code=404, detail="Location non trouvée")

    media = await store.fetch_one(rental.media_id)
    other_rentals = await store.list_rentals_for_media(rental.media_id)
    still_in_use = any(
        other.id != rental.id and (other.status in {"requested", "downloading", "available", "keep_requested", "kept"}
                                   or other.storage_policy == "permanent")
        for other in other_rentals
    )
    removed = False
    warning = None
    if media and media.type == "Film" and not still_in_use:
        try:
            if was_pending:
                removed = await service.cancel_pending_movie(media.id)
            else:
                await service.delete_storage_candidate(media.id, current.user["id"], allow_protected=True)
                removed = True
        except LookupError:
            # The download may not have arrived yet; the rental is still revoked.
            pass
        except (PermissionError, RuntimeError, MediaServerError) as error:
            warning = str(error)
    elif media and media.type == "Série" and not still_in_use:
        warning = "L'accès de location est révoqué, mais la série reste dans Sonarr/Jellyfin."

    title = f"« {media.title} »" if media else "Ton film"
    message = f"{title} : l'accès à la location a été révoqué par l'administrateur."
    await store.create_notification(Notification(
        id=str(uuid.uuid4()), backstage_user_id=rental.backstage_user_id,
        kind="rental_revoked", message=message, created_at=now,
    ))
    return {
        "rental": _serialize_rental(rental),
        "removed_from_library": removed,
        "retained_for_other_rentals": still_in_use,
        "warning": warning,
    }


@router.get("/notifications")
async def list_notifications(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    notifications = await store.list_notifications(current.user["id"])
    return {"notifications": [_serialize_notification(item) for item in notifications]}


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    if not await store.mark_notification_read(notification_id, current.user["id"], datetime.now(timezone.utc)):
        raise HTTPException(status_code=404, detail="Notification non trouvée")
    return {"ok": True}


CHAT_MESSAGE_MAX_LENGTH = 500


class PostChatMessageRequest(BaseModel):
    body: str


@router.get("/chat/messages")
async def list_chat_messages(
    after: Optional[int] = None,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    return {"messages": await store.list_chat_messages(after, viewer_id=current.user["id"])}


@router.post("/chat/messages")
async def post_chat_message(
    payload: PostChatMessageRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Le message est vide.")
    if len(body) > CHAT_MESSAGE_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Message trop long ({CHAT_MESSAGE_MAX_LENGTH} caractères max).")
    user = current.user
    # Les commandes de bot (@ciné, @soirée) et leurs réponses ne regardent que celui qui demande.
    is_command = cinema_bot.parse_command(body) is not None or is_party_command(body)
    message = await store.create_chat_message(
        user["id"], user.get("display_name") or "Anonyme", user.get("avatar_url"), body,
        visible_to=user["id"] if is_command else None,
    )
    try:
        await cinema_bot.handle_chat_message(body, store, visible_to=user["id"])
    except Exception:
        logger.exception("[cinema] Le bot n'a pas pu répondre")
    try:
        await PartyService(store).handle_chat_message(body, user)
    except Exception:
        logger.exception("[soirée] Le bot n'a pas pu répondre")
    return message


@router.get("/media-server/options")
async def media_server_options(
    media_type: str,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    client = service.sonarr if media_type == "Série" else service.radarr
    if not client:
        raise HTTPException(status_code=503, detail="Les demandes sont indisponibles pour le moment (service de téléchargement non configuré). Préviens l'administrateur.")
    options = await client.list_options()
    if media_type == "Film":
        profile_name = Config.RADARR_DEFAULT_QUALITY_PROFILE_NAME
        default_profile = next(
            (item for item in options.get("quality_profiles", []) if item.get("name") == profile_name),
            None,
        )
        options = {
            **options,
            "default_quality_profile_id": default_profile.get("id") if default_profile else None,
            "default_quality_profile_name": profile_name,
        }
        if current.user.get("role") != "admin":
            options["quality_profiles"] = [default_profile] if default_profile else []
    return options


@router.post("/media-server/sync", dependencies=[Depends(require_admin)])
async def sync_media_server(service: MediaServerService = Depends(get_media_server_service)):
    if not Config.media_server_enabled():
        raise HTTPException(status_code=503, detail="Service non configuré")
    return await service.sync_all()


@router.post("/media-server/import", dependencies=[Depends(require_admin)])
async def import_media_server_library(service: MediaServerService = Depends(get_media_server_service)):
    if not Config.media_server_enabled():
        raise HTTPException(status_code=503, detail="Service non configuré")
    return await service.import_existing_libraries()


@router.get("/media-server/activity", dependencies=[Depends(require_admin)])
async def media_server_activity(service: MediaServerService = Depends(get_media_server_service)):
    return await service.activity()


@router.get("/admin/storage/status")
async def admin_storage_status(
    _: AuthContext = Depends(require_admin),
    service: MediaServerService = Depends(get_media_server_service),
):
    return await service.storage_status()


@router.get("/admin/storage/candidates")
async def admin_storage_candidates(
    _: AuthContext = Depends(require_admin),
    service: MediaServerService = Depends(get_media_server_service),
    store: MediaStore = Depends(get_store),
):
    candidates = await service.storage_candidates()
    return {
        "candidates": [item.model_dump(mode="json") for item in candidates],
        "history": await store.list_storage_cleanup_log(),
    }


@router.post("/admin/storage/candidates/{media_id}/protection")
async def admin_storage_candidate_protection(
    media_id: str,
    payload: StorageProtectionRequest,
    _: AuthContext = Depends(require_admin),
    service: MediaServerService = Depends(get_media_server_service),
):
    if not await service.set_storage_protection(media_id, payload.protected):
        raise HTTPException(status_code=404, detail="Film non trouvé")
    return {"media_id": media_id, "protected": payload.protected}


@router.delete("/admin/storage/candidates/{media_id}")
async def admin_delete_storage_candidate(
    media_id: str,
    current: AuthContext = Depends(require_admin),
    service: MediaServerService = Depends(get_media_server_service),
):
    try:
        return await service.delete_storage_candidate(media_id, current.user["id"])
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except MediaServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/admin/storage/expired/delete")
async def admin_delete_expired_rentals(
    current: AuthContext = Depends(require_admin),
    service: MediaServerService = Depends(get_media_server_service),
):
    try:
        return await service.delete_expired_rentals(current.user["id"])
    except MediaServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/admin/dashboard")
async def admin_dashboard(
    _: AuthContext = Depends(require_admin),
    service: MediaServerService = Depends(get_media_server_service),
    store: MediaStore = Depends(get_store),
    auth_store: AuthStore = Depends(get_auth_store),
):
    now = datetime.now(timezone.utc)
    activity = await service.activity()
    availabilities = activity.get("items", [])
    rentals = await store.list_admin_rentals()
    users = {user["id"]: user["display_name"] for user in auth_store.list_users()}
    expiring = []
    for item in rentals:
        rental = item["rental"]
        if rental.expires_at and rental.expires_at <= now + timedelta(days=3):
            expiring.append({
                "media_title": item["media_title"],
                "requester_name": users.get(rental.backstage_user_id, "Compte supprimé"),
                "rental": _serialize_rental(rental),
            })
    return {
        "expiring": expiring,
        "downloads": [item for item in availabilities if item.get("state") in {"requested", "searching", "downloading"}],
        "errors": [item for item in availabilities if item.get("state") == "error" or item.get("last_error")],
        "services": {
            "radarr": {"configured": Config.radarr_enabled()},
            "sonarr": {"configured": Config.sonarr_enabled()},
            "seerr": {"configured": Config.seerr_enabled()},
            "jellyfin": {"configured": Config.jellyfin_enabled()},
        },
        "storage": await service.storage_status(),
        "quotas": [
            {
                "user_id": user["id"],
                "display_name": user["display_name"],
                **(lambda slots: {"active_rentals": slots["in_use"], "queued_rentals": slots["queued"]})(
                    await store.count_rental_slots(user["id"])
                ),
                "temporary_bytes": await store.active_temporary_bytes(user["id"]),
                "max_active_rentals": MAX_ACTIVE_RENTALS,
                "max_queued_rentals": MAX_QUEUED_RENTALS,
            }
            for user in auth_store.list_users()
            if user["role"] != "admin"
        ],
    }


@router.get("/admin/system/backup")
async def admin_backup_status(_: AuthContext = Depends(require_admin)):
    return await asyncio.to_thread(get_backup_status, Config.BACKUP_DIR)


@router.post("/admin/system/backup")
async def admin_create_backup(_: AuthContext = Depends(require_admin)):
    try:
        return await asyncio.to_thread(
            create_backup, Config.DB_PATH, Config.BACKUP_DIR,
            retention_days=Config.BACKUP_RETENTION_DAYS,
        )
    except (OSError, sqlite3.Error, RuntimeError) as error:
        raise HTTPException(status_code=503, detail=f"Sauvegarde impossible : {error}") from error


@router.post("/admin/system/backup/verify")
async def admin_verify_backup(_: AuthContext = Depends(require_admin)):
    status = await asyncio.to_thread(get_backup_status, Config.BACKUP_DIR)
    latest = status.get("latest")
    if not latest:
        raise HTTPException(status_code=404, detail="Aucune sauvegarde à vérifier")
    result = await asyncio.to_thread(verify_backup, latest["path"])
    if result["integrity"] != "ok" or not result["readable"]:
        raise HTTPException(status_code=503, detail=result)
    return result


def _serialize_playback_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "resume": [item.model_dump(mode="json") for item in summary["resume"]],
        "next_episodes": summary["next_episodes"],
        "recently_completed": [item.model_dump(mode="json") for item in summary["recently_completed"]],
        "last_synced_at": summary["last_synced_at"].isoformat() if summary["last_synced_at"] else None,
    }


@router.post("/playback/sync")
async def sync_playback(
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    jellyfin_user_id = current.user.get("jellyfin_user_id")
    if not jellyfin_user_id:
        return {"linked": False, "synced": 0}
    try:
        result = await service.sync_playback(current.user["id"], jellyfin_user_id)
    except (httpx.HTTPError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail="Progression Jellyfin indisponible") from error
    return {"linked": True, **result}


@router.get("/playback/summary")
async def playback_summary(
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    summary = _serialize_playback_summary(await service.playback_summary(current.user["id"]))
    return {"linked": bool(current.user.get("jellyfin_user_id")), **summary}
