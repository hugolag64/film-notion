"""FastAPI REST API for Backstage UI integration."""
from datetime import datetime, timedelta, timezone
import uuid
from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.config import Config
from backend.core.store import MediaStore
from backend.core.models import Media, Notification, Rental

from backend.core.tmdb import TMDBClient
from backend.core.mapping import is_series
from backend.core.tmdb_relink import build_relink_updates
from backend.core.arr import RadarrClient, SonarrClient, MediaServerError
from backend.core.seerr import SeerrClient
from backend.core.jellyfin import JellyfinClient
from backend.core.media_server import MediaServerService
from backend.auth_api import AuthContext, get_auth_store, get_current_user, require_admin
from backend.core.auth import AuthStore
from urllib.parse import quote, parse_qsl, urlencode, urlsplit

router = APIRouter(
    prefix="/api",
    tags=["medias"],
    dependencies=[Depends(get_current_user)],
)
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health_check():
    return {"status": "ok"}


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
    details = await tmdb.get_details(payload.tmdb_id, is_series=is_series(media.type))
    if not details:
        raise HTTPException(status_code=400, detail="Impossible de récupérer les détails TMDB pour cet ID")

    await store.update(media_id, build_relink_updates(media, details, tmdb, payload.tmdb_id))
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


@router.get("/medias/{media_id}/episodes")
async def get_series_episodes(media_id: str, store: MediaStore = Depends(get_store)):
    media = await store.fetch_one(media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Média non trouvé")

    return {
        "episodes": await store.list_episodes(media_id),
        "progress": await store.series_progress(media_id),
    }


@router.patch("/episodes/{episode_id}")
async def update_episode(
    episode_id: str,
    payload: UpdateEpisodeRequest,
    store: MediaStore = Depends(get_store),
):
    episode = await store.set_episode_watched(episode_id, payload.watched)
    if not episode:
        raise HTTPException(status_code=404, detail="Épisode non trouvé")

    return {
        "episode": episode,
        "progress": await store.series_progress(episode["media_id"]),
    }


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


@router.post("/series/from_tmdb", response_model=Media)
async def create_series_from_tmdb_endpoint(
    payload: CreateFromTMDBRequest,
    store: MediaStore = Depends(get_store),
):
    return await create_series_from_tmdb(payload, store, TMDBClient())


@router.post("/series/{media_id}/refresh", response_model=Media)
async def refresh_series_from_tmdb_endpoint(
    media_id: str,
    store: MediaStore = Depends(get_store),
):
    return await refresh_series_from_tmdb(media_id, store, TMDBClient())


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


@router.get("/medias/{media_id}/availability")
async def get_availability(
    media_id: str,
    service: MediaServerService = Depends(get_media_server_service),
):
    availability = await service.store.get_availability(media_id)
    playback_url = await service.playback_url(media_id)
    return {"availability": availability, "playback_url": playback_url}


@router.get("/medias/{media_id}/playback/manifest")
async def get_playback_manifest(
    media_id: str,
    service: MediaServerService = Depends(get_media_server_service),
):
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
    service: MediaServerService = Depends(get_media_server_service),
):
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
                status=availability.state, requested_at=now, created_at=now, updated_at=now,
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
        "accepted": ("retention_accepted", "Votre film a été conservé définitivement."),
        "refused": ("retention_refused", "La demande de conservation de votre film a été refusée."),
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
