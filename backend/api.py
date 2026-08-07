"""FastAPI REST API for Backstage UI integration."""
from datetime import datetime, timedelta, timezone
import asyncio
import logging
import sqlite3
import uuid
from random import Random
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
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
from backend.core.arr import RadarrClient, SonarrClient, MediaServerError
from backend.core.seerr import SeerrClient
from backend.core.jellyfin import JellyfinClient
from backend.core.media_server import MediaServerService
from backend.core.backup import create_backup, get_backup_health, get_backup_status, verify_backup
from backend.core.recommendations import (
    RecommendationCandidate, TasteProfile, build_local_question, build_taste_profile,
    choose_from_top, score_candidate, score_recommendation_candidate,
)
from backend.core.gemini_recommendations import GeminiRecommendationGateway, SUPPORTED_QUESTION_AXES
from backend.auth_api import AuthContext, get_auth_store, get_current_user, require_admin
from backend.core.auth import AuthStore
from urllib.parse import quote, parse_qsl, urlencode, urlsplit

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


def _rewrite_hls_manifest(manifest: str, media_id: str) -> str:
    rewritten = []
    for line in manifest.splitlines():
        if not line or line.startswith("#"):
            rewritten.append(line)
            continue
        parsed = urlsplit(line)
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() != "api_key"]
        resource = f"/api/medias/{quote(media_id, safe='')}/playback/resource/{quote(parsed.path, safe='/')}"
        if query:
            resource += f"?{urlencode(query)}"
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
    limit = max(0, int(getattr(Config, "RECOMMENDATION_DAILY_LIMIT", 2)))
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
    plans: dict[str, list[str]] = {}
    for event in reversed(events):
        value = str(event.value or "")
        if event.event_type != "question_answered" or not value.startswith("plan:") or not event.session_id:
            continue
        axis = value.removeprefix("plan:")
        if axis in SUPPORTED_QUESTION_AXES:
            plans.setdefault(event.session_id, []).append(axis)
    return list(plans.values())[-4:]


def _fallback_question_plan(recent_axes: list[str]) -> list[str]:
    recent = set(recent_axes[-len(SUPPORTED_QUESTION_AXES):])
    fresh = [axis for axis in SUPPORTED_QUESTION_AXES if axis not in recent]
    return (fresh + [axis for axis in SUPPORTED_QUESTION_AXES if axis not in fresh])[:5]


def _vary_question_plan(plan: list[str], recent_plans: list[list[str]], recent_axes: list[str]) -> list[str]:
    normalized = list(dict.fromkeys(axis for axis in plan if axis in SUPPORTED_QUESTION_AXES))
    if not normalized:
        return _fallback_question_plan(recent_axes)
    recent = [item for item in recent_plans[-4:] if item]
    for offset in range(len(normalized)):
        candidate = normalized[offset:] + normalized[:offset]
        if candidate not in recent:
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


class RecommendationConfirmRequest(BaseModel):
    tmdb_id: int
    download: bool = True


class RelinkTMDBRequest(BaseModel):
    tmdb_id: int


class CreateFromTMDBRequest(BaseModel):
    tmdb_id: int


class UpdateEpisodeRequest(BaseModel):
    watched: bool


class AcquisitionRequest(BaseModel):
    quality_profile_id: Optional[int] = None
    root_folder: Optional[str] = None
    language_profile_id: Optional[int] = None
    monitor: str = "all"


MAX_ACTIVE_RENTALS = 5


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


async def _media_for_user(media: Media, current: AuthContext, store: MediaStore) -> Media:
    state = await store.get_user_media_state(current.user["id"], media.id)
    if state is None and current.user["role"] == "admin":
        if media.rating and str(media.rating).strip():
            return media.model_copy(update={"status": "Terminé", "is_watchlist": False})
        return media
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
    return media.model_copy(update=updates)


@router.get("/medias", response_model=List[Media])
async def list_medias(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    medias = await store.fetch_all()
    return [await _media_for_user(media, current, store) for media in medias]


@router.get("/medias/{media_id}", response_model=Media)
async def get_media(
    media_id: str,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    return await _media_for_user(media, current, store)

@router.get("/medias/{media_id}/tmdb-rating")
async def get_tmdb_rating(media_id: str, store: MediaStore = Depends(get_store)):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")
    if not media.tmdb_id:
        return {"rating": None}
    try:
        details = await TMDBClient().get_movie_details(media.tmdb_id)
    except Exception as error:
        logger.warning("Note TMDB indisponible pour le média %s : %s", media_id, error)
        return {"rating": None}
    raw_rating = details.get("vote_average") if details else None
    try:
        rating = float(raw_rating) if raw_rating is not None else None
    except (TypeError, ValueError):
        rating = None
    return {"rating": rating}


@router.patch("/medias/{media_id}/personal", response_model=Media)
async def update_personal_media(
    media_id: str,
    payload: UpdatePersonalMediaRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
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
    return await _media_for_user(media, current, store)


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
    try:
        tmdb = TMDBClient()
        candidates = await tmdb.discover_movies(page=1, min_vote_count=25)
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
    if recent_shown_tmdb_ids and sum(item.score >= 0 for item in scored) < 2:
        # A cooldown is a soft memory, never a reason to show an empty screen.
        scored = score_pool(hard_seen_tmdb_ids)
    return scored


def _serialize_recommendation(candidate: RecommendationCandidate | None) -> dict[str, Any] | None:
    return candidate.model_dump(mode="json") if candidate else None


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
    return (await store.record_recommendation_event(event)).model_dump(mode="json")


@router.post("/recommendations/sessions")
async def start_recommendation_session(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    quota = _recommendation_quota(current, store, datetime.now(timezone.utc))
    if not quota["unlimited"] and quota["remaining"] <= 0:
        raise HTTPException(
            status_code=429,
            detail="Limite quotidienne atteinte : 2 sessions de sélection par jour.",
        )
    session = RecommendationSession(
        id=str(uuid.uuid4()),
        backstage_user_id=current.user["id"],
        created_at=datetime.now(timezone.utc),
    )
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
    if quota["unlimited"]:
        await store.create_recommendation_session(session)
    else:
        reserved = await store.create_recommendation_session_if_available(
            session, quota["limit"], _recommendation_day_start(datetime.now(timezone.utc)),
        )
        if reserved is None:
            raise HTTPException(
                status_code=429,
                detail="Limite quotidienne atteinte : 2 sessions de sélection par jour.",
            )
        quota["used"] += 1
        quota["remaining"] = max(0, quota["limit"] - quota["used"])
    for axis in question_plan:
        await store.record_recommendation_event(RecommendationEvent(
            id=str(uuid.uuid4()), backstage_user_id=current.user["id"],
            session_id=session.id, event_type="question_answered", value=f"plan:{axis}",
            created_at=datetime.now(timezone.utc),
        ))
    await _remember_question_options(session, question, store)
    return {"session": session.model_dump(mode="json"), "state": "question", "question": question, "result": None, "quota": quota}


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
    events = await store.list_recommendation_events(current.user["id"])
    selected = any(
        event.session_id == session_id
        and event.event_type == "session_completed"
        and str(event.value) == str(payload.tmdb_id)
        for event in events
    )
    if not selected:
        raise HTTPException(status_code=403, detail="Ce film ne correspond pas à la recommandation validée")

    media = next((item for item in await store.fetch_all() if item.type == "Film" and item.tmdb_id == payload.tmdb_id), None)
    if media is None:
        tmdb = TMDBClient()
        details = await tmdb.get_movie_details(payload.tmdb_id)
        if not details:
            raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB")
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

    availability = await store.get_availability(media.id)
    download_error = None
    if payload.download and not availability:
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


@router.get("/medias/{media_id}/episodes")
async def get_series_episodes(
    media_id: str,
    store: MediaStore = Depends(get_store),
    current: AuthContext = Depends(get_current_user),
):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    if isinstance(current, AuthContext):
        episodes = await store.list_episodes_for_user(media_id, current.user["id"])
        progress = await store.series_progress_for_user(media_id, current.user["id"])
    else:
        episodes = await store.list_episodes(media_id)
        progress = await store.series_progress(media_id)
    return {"episodes": episodes, "progress": progress}


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

    episodes = await _fetch_tmdb_series_episodes(payload.tmdb_id, details, tmdb)

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
    await store.create_episodes(series.id, episodes)
    return await store.fetch_one(series.id)


async def _fetch_tmdb_series_episodes(
    tmdb_id: int, details: Dict[str, Any], tmdb: TMDBClient,
) -> List[Dict[str, Any]]:
    """Load every non-special TMDB episode for an import or refresh."""
    episodes: List[Dict[str, Any]] = []
    for season in details.get("seasons") or []:
        season_number = season.get("season_number")
        if not isinstance(season_number, int) or season_number <= 0:
            continue
        season_details = await tmdb.get_tv_season_details(tmdb_id, season_number)
        if season_details is None:
            raise HTTPException(
                status_code=502,
                detail="Impossible de récupérer les épisodes TMDB",
            )
        for episode in (season_details or {}).get("episodes") or []:
            episode_number = episode.get("episode_number")
            if not isinstance(episode_number, int):
                continue
            episodes.append({
                "season_number": season_number,
                "episode_number": episode_number,
                "title": episode.get("name") or "Sans titre",
                "synopsis": (episode.get("overview") or "")[:2000],
                "watched": False,
            })
    return episodes


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
    episodes = await _fetch_tmdb_series_episodes(tmdb_id, details, tmdb)
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
    await store.upsert_episodes(media_id, episodes)
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



@router.get("/media-server/status")
async def media_server_status():
    return {
        "radarr": {"configured": Config.radarr_enabled()},
        "sonarr": {"configured": Config.sonarr_enabled()},
        "seerr": {"configured": Config.seerr_enabled()},
        "jellyfin": {"configured": Config.jellyfin_enabled()},
    }


_PLAYBACK_RENTAL_STATES = {"available", "keep_requested", "kept"}


async def _ensure_playback_access(
    current: AuthContext, media_id: str, store: MediaStore,
) -> Optional[Rental]:
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="MÃ©dia non trouvÃ©")
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
    raise HTTPException(status_code=403, detail="Vous n'avez pas accès à ce contenu")


@router.get("/medias/{media_id}/availability")
async def get_availability(
    media_id: str,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    await _ensure_playback_access(current, media_id, service.store)
    availability = await service.store.get_availability(media_id)
    playback_url = await service.playback_url(media_id)
    return {"availability": availability, "playback_url": playback_url}


@router.get("/medias/{media_id}/playback/manifest")
async def get_playback_manifest(
    media_id: str,
    current: AuthContext = Depends(get_current_user),
    service: MediaServerService = Depends(get_media_server_service),
):
    await _ensure_playback_access(current, media_id, service.store)
    playback = await service.playback_manifest(media_id)
    if not playback or not service.jellyfin:
        raise HTTPException(status_code=404, detail="Lecture indisponible")
    try:
        response = await service.jellyfin.fetch_playback_resource(
            playback["item_id"], "master.m3u8",
            {"VideoCodec": "h264", "AudioCodec": "aac", "Container": "ts",
             "TranscodingContainer": "ts", "TranscodingProtocol": "hls",
             "MaxWidth": "1920", "MaxHeight": "1080", "MediaSourceId": playback["item_id"]},
        )
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Flux Jellyfin indisponible") from None
    manifest = _rewrite_hls_manifest(response.text, media_id)
    return Response(content=manifest, media_type="application/vnd.apple.mpegurl")


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
        response = await service.playback_resource(media_id, resource_path, query)
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Ressource Jellyfin indisponible") from None
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
    if not media.tmdb_id:
        raise HTTPException(status_code=409, detail="Associez d'abord ce média à TMDB")
    is_admin = current.user.get("role") == "admin"
    owner_id = current.user["id"]
    if not is_admin:
        existing_rental = await service.store.find_active_rental(owner_id, media_id)
        if existing_rental:
            return {
                "availability": await service.store.get_availability(media_id),
                "rental": _serialize_rental(existing_rental),
            }
        if await service.store.count_active_rentals(owner_id) >= MAX_ACTIVE_RENTALS:
            raise HTTPException(status_code=409, detail="Limite de 5 locations actives atteinte")
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
                status=availability.state, rental_scope="series" if media.type == "Série" else "movie",
                requested_at=now, created_at=now, updated_at=now,
            ))
            response["rental"] = _serialize_rental(rental)
        return response
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except MediaServerError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="Service non configuré") from error


@router.get("/rentals")
async def list_rentals(
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    if current.user.get("role") == "admin":
        return {"rentals": []}
    rentals = await store.list_user_rentals(current.user["id"])
    return {"rentals": [_serialize_rental(rental) for rental in rentals]}


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
    messages = {
        "accepted": ("retention_accepted", "Votre contenu a été conservé définitivement."),
        "refused": ("retention_refused", "La demande de conservation de votre contenu a été refusée."),
    }
    kind, message = messages[decision]
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
        kind="retention_extended", message="Votre location a été prolongée de 7 jours.", created_at=now,
    ))
    return {"rental": _serialize_rental(rental)}


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


@router.get("/media-server/options")
async def media_server_options(
    media_type: str,
    service: MediaServerService = Depends(get_media_server_service),
):
    client = service.sonarr if media_type == "Série" else service.radarr
    if not client:
        raise HTTPException(status_code=503, detail="Service non configuré")
    return await client.list_options()


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
                "active_rentals": await store.count_active_rentals(user["id"]),
                "temporary_bytes": await store.active_temporary_bytes(user["id"]),
                "max_active_rentals": MAX_ACTIVE_RENTALS,
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
