"""Shared models for the local media-server integration."""
from datetime import datetime, timedelta
from datetime import timezone
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.core.playback import PlaybackProgress
from backend.config import Config
from backend.core.seerr import SeerrDuplicateRequest
from backend.core.series_episodes import ensure_series_episodes
from backend.core.tmdb import TMDBClient


logger = logging.getLogger(__name__)
STALE_REQUEST_GRACE = timedelta(hours=1)
HARD_STORAGE_PROTECTION_REASONS = {"favorite", "active_rental", "manual"}
# (source, external id, is_series) -> TMDB id, so each sync does not ask TMDB again.
_EXTERNAL_TMDB_IDS: dict[tuple[str, str, bool], int] = {}
# Medias already enriched once in this process (avoid a TMDB call per sync).
_ENRICHED_MEDIA_IDS: set[tuple[str, str]] = set()


def _optional_tmdb():
    try:
        return TMDBClient()
    except ValueError:
        return None


async def _lookup_tmdb_id(tmdb, external_ids: list[tuple[str, Any]], is_series: bool) -> Optional[int]:
    """Translate the first resolvable TVDB/IMDb id into a TMDB id."""
    if tmdb is None or not hasattr(tmdb, "find_tmdb_id"):
        return None
    for source, value in external_ids:
        if not value:
            continue
        key = (source, str(value), is_series)
        if key not in _EXTERNAL_TMDB_IDS:
            found = await tmdb.find_tmdb_id(str(value), source, is_series)
            if not found:
                continue  # not cached: a TMDB outage must not hide the item forever
            _EXTERNAL_TMDB_IDS[key] = found
        return _EXTERNAL_TMDB_IDS[key]
    return None


async def resolve_jellyfin_tmdb_ids(items: list[dict[str, Any]], tmdb) -> list[dict[str, Any]]:
    """Fill ``tmdb_id`` on Jellyfin items only known by TVDB/IMDb ids."""
    resolved = []
    for item in items:
        if item.get("tmdb_id") is None:
            tmdb_id = await _lookup_tmdb_id(
                tmdb, [("tvdb_id", item.get("tvdb_id")), ("imdb_id", item.get("imdb_id"))],
                item.get("media_type") == "Série",
            )
            item = {**item, "tmdb_id": tmdb_id}
        resolved.append(item)
    return resolved


async def resolve_arr_tmdb_ids(items: list[dict[str, Any]], tmdb, is_series: bool) -> list[dict[str, Any]]:
    """Sonarr v3 only exposes ``tvdbId``: translate it so TMDB matching works."""
    resolved = []
    for item in items:
        if not item.get("tmdbId"):
            tmdb_id = await _lookup_tmdb_id(
                tmdb, [("tvdb_id", item.get("tvdbId")), ("imdb_id", item.get("imdbId"))], is_series,
            )
            if tmdb_id:
                item = {**item, "tmdbId": tmdb_id}
        resolved.append(item)
    return resolved


AvailabilityState = Literal[
    "requested", "searching", "downloading", "imported", "available", "error",
]
Provider = Literal["radarr", "sonarr"]


class Availability(BaseModel):
    media_id: str
    provider: Provider
    arr_id: Optional[int] = None
    jellyfin_id: Optional[str] = None
    state: AvailabilityState = "requested"
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)
    root_folder: Optional[str] = None
    quality_profile_id: Optional[int] = None
    language_profile_id: Optional[int] = None
    last_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None


class StorageCandidate(BaseModel):
    media_id: str
    title: str
    tmdb_id: Optional[int] = None
    radarr_id: int
    path: Optional[str] = None
    size_bytes: int = Field(default=0, ge=0)
    added_at: Optional[datetime] = None
    last_played_at: Optional[datetime] = None
    is_favorite: bool = False
    has_active_rental: bool = False
    rental_expired: bool = False
    protected: bool = False
    protection_reasons: list[str] = Field(default_factory=list)


class MediaServerService:
    """Maps Arr/Jellyfin state into durable, UI-safe availability records."""

    def __init__(self, store, *, radarr=None, sonarr=None, jellyfin=None, seerr=None):
        self.store = store
        self.radarr = radarr
        self.sonarr = sonarr
        self.jellyfin = jellyfin
        self.seerr = seerr

    async def _jellyfin_library(self, tmdb=None) -> list[dict[str, Any]]:
        items = await self.jellyfin.list_library()
        return await resolve_jellyfin_tmdb_ids(items, tmdb if tmdb is not None else _optional_tmdb())

    async def _arr_library(self, client, is_series: bool, tmdb=None) -> list[dict[str, Any]]:
        items = await client.list_library()
        if not is_series:
            return items
        return await resolve_arr_tmdb_ids(items, tmdb if tmdb is not None else _optional_tmdb(), True)

    async def sonarr_defaults(self) -> dict[str, Any]:
        """Quality profile / root folder / language used for one-click series downloads."""
        if self.sonarr is None:
            raise RuntimeError("Sonarr n'est pas configuré")
        options = await self.sonarr.list_options()
        profiles = options.get("quality_profiles") or []
        wanted = Config.SONARR_DEFAULT_QUALITY_PROFILE_NAME
        profile = next((item for item in profiles if wanted and item.get("name") == wanted), None) or (
            profiles[0] if profiles else None
        )
        if profile is None or profile.get("id") is None:
            raise ValueError("Aucun profil qualité Sonarr disponible")
        root_folder = Config.SONARR_DEFAULT_ROOT_FOLDER or next(
            (item.get("path") for item in options.get("root_folders") or [] if item.get("path")), None,
        )
        if not root_folder:
            raise ValueError("Aucun dossier racine Sonarr disponible")
        languages = options.get("language_profiles") or []
        return {
            "quality_profile_id": int(profile["id"]),
            "root_folder": root_folder,
            "language_profile_id": languages[0].get("id") if languages else None,
        }

    async def _add_series_parts(
        self, media, quality_profile_id: Optional[int], root_folder: Optional[str],
        language_profile_id: Optional[int], seasons: Optional[list[int]],
        episodes: Optional[list[tuple[int, int]]],
    ) -> dict[str, Any]:
        """Request only some seasons or episodes of a series."""
        if episodes or not self.seerr:
            # Seerr cannot request single episodes: talk to Sonarr directly.
            if self.sonarr is None:
                raise RuntimeError("Le téléchargement à l'épisode nécessite Sonarr")
            if quality_profile_id is None or not root_folder:
                defaults = await self.sonarr_defaults()
                quality_profile_id = quality_profile_id or defaults["quality_profile_id"]
                root_folder = root_folder or defaults["root_folder"]
                language_profile_id = language_profile_id or defaults["language_profile_id"]
            series = await self.sonarr.ensure_series(
                media.tmdb_id, quality_profile_id, language_profile_id, root_folder,
            )
            if episodes:
                await self.sonarr.search_episodes(series, episodes)
            for season_number in seasons or []:
                await self.sonarr.search_season(series, season_number)
            return series
        try:
            return await self.seerr.request_media(
                tmdb_id=media.tmdb_id, media_type=media.type,
                quality_profile_id=quality_profile_id, root_folder=root_folder,
                language_profile_id=language_profile_id, monitor="all", seasons=seasons,
            )
        except SeerrDuplicateRequest:
            return {}

    async def add(
        self, media, quality_profile_id: Optional[int], root_folder: Optional[str],
        language_profile_id: Optional[int], monitor: str,
        seasons: Optional[list[int]] = None, episodes: Optional[list[tuple[int, int]]] = None,
    ) -> Availability:
        if not media.tmdb_id:
            raise ValueError("Associe d'abord ce film à TMDB")
        provider = "sonarr" if media.type == "Série" else "radarr"
        if media.type == "Série" and (seasons or episodes):
            remote = await self._add_series_parts(
                media, quality_profile_id, root_folder, language_profile_id, seasons, episodes,
            )
            current = await self.store.get_availability(media.id)
            if current and (current.jellyfin_id or current.state in {"searching", "downloading", "imported"}):
                # Part of the series is already there or coming: keep that state.
                return current
            return await self.store.upsert_availability(Availability(
                media_id=media.id, provider=provider,
                arr_id=None if (self.seerr and not episodes) else remote.get("id"),
                state="requested", root_folder=root_folder,
                quality_profile_id=quality_profile_id, language_profile_id=language_profile_id,
                last_synced_at=datetime.now(timezone.utc),
            ))
        if self.seerr:
            try:
                remote = await self.seerr.request_media(
                    tmdb_id=media.tmdb_id, media_type=media.type,
                    quality_profile_id=quality_profile_id, root_folder=root_folder,
                    language_profile_id=language_profile_id, monitor=monitor,
                )
            except SeerrDuplicateRequest:
                # Already requested in Seerr (from Backstage or elsewhere): track it, don't fail.
                remote = {}
        elif media.type == "Série":
            if not self.sonarr or quality_profile_id is None or not root_folder or language_profile_id is None:
                raise RuntimeError("Sonarr n'est pas configuré")
            remote = await self.sonarr.add_series(
                media.tmdb_id, quality_profile_id, language_profile_id, root_folder, monitor,
            )
        else:
            if not self.radarr or quality_profile_id is None or not root_folder:
                raise RuntimeError("Radarr n'est pas configuré")
            remote = await self.radarr.add_movie(media.tmdb_id, quality_profile_id, root_folder)
        return await self.store.upsert_availability(Availability(
            media_id=media.id, provider=provider, arr_id=None if self.seerr else remote.get("id"),
            state="requested", root_folder=root_folder,
            quality_profile_id=quality_profile_id, language_profile_id=language_profile_id,
            last_synced_at=datetime.now(timezone.utc),
        ))

    async def acquisition_defaults(self, media) -> dict[str, Any]:
        if self.radarr is None:
            if self.seerr is not None:
                return {"quality_profile_id": None, "root_folder": None, "language_profile_id": None, "monitor": "all"}
            raise RuntimeError("Aucun service de téléchargement n'est configuré")
        options = await self.radarr.list_options()
        profile_name = Config.RADARR_DEFAULT_QUALITY_PROFILE_NAME
        profile = next((item for item in options.get("quality_profiles", []) if item.get("name") == profile_name), None)
        if profile is None or profile.get("id") is None:
            raise ValueError(f"Profil qualité administrateur introuvable : {profile_name}")
        root_folder = Config.RADARR_DEFAULT_ROOT_FOLDER
        if not root_folder:
            root_folder = next((item.get("path") for item in options.get("root_folders", []) if item.get("path")), None)
        if not root_folder:
            raise ValueError("Aucun dossier racine Radarr disponible")
        return {
            "quality_profile_id": int(profile["id"]), "root_folder": root_folder,
            "language_profile_id": None, "monitor": "all",
        }

    async def add_with_defaults(self, media) -> Availability:
        return await self.add(media, **(await self.acquisition_defaults(media)))

    async def _find_jellyfin_match(self, media, library_items=None) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        if not self.jellyfin:
            return None, None
        jellyfin_error = None
        if library_items is None and hasattr(self.jellyfin, "list_library"):
            try:
                library_items = await self._jellyfin_library()
            except Exception as error:
                library_items = None
                jellyfin_error = "Jellyfin indisponible"
                logger.warning("[jellyfin-sync] Library lookup failed for %s: %s", media.id, error)
        if library_items is not None:
            match = next((item for item in library_items
                          if item.get("tmdb_id") == media.tmdb_id and item.get("media_type") == media.type), None)
            if match:
                return match, None
        if hasattr(self.jellyfin, "find_by_tmdb"):
            try:
                item = await self.jellyfin.find_by_tmdb(media.tmdb_id, media.type)
            except Exception as error:
                logger.warning("[jellyfin-sync] Item lookup failed for %s: %s", media.id, error)
                return None, "Jellyfin indisponible"
            if item and item.get("Id"):
                return {"jellyfin_id": str(item["Id"]), "tmdb_id": media.tmdb_id, "media_type": media.type}, None
        return None, jellyfin_error

    async def _save_jellyfin_availability(
        self, media, provider: Provider, jellyfin_item: dict[str, Any], remote: Optional[dict[str, Any]] = None,
    ) -> Availability:
        current = await self.store.get_availability(media.id)
        availability = Availability(
            media_id=media.id,
            provider=provider,
            arr_id=(remote or {}).get("id") if remote else (current.arr_id if current else None),
            jellyfin_id=jellyfin_item.get("jellyfin_id") or jellyfin_item.get("Id"),
            state="available",
            last_synced_at=datetime.now(timezone.utc),
        )
        if availability.arr_id is not None:
            await self.store.clear_arr_id_conflict(provider, availability.arr_id, media.id)
        saved = await self.store.upsert_availability(availability)
        available_at = datetime.now(timezone.utc)
        size_bytes = (remote or {}).get("sizeOnDisk")
        if not isinstance(size_bytes, (int, float)) or size_bytes < 0:
            size_bytes = None
        await self.store.mark_rentals_available(
            media.id, available_at, available_at + timedelta(days=21),
            int(size_bytes) if size_bytes is not None else None,
        )
        await self.store.update(media.id, {"support": "Serveur"})
        if media.type == "Série" and availability.jellyfin_id:
            await self._release_season_rentals(media, availability.jellyfin_id, available_at)
        return saved

    async def seasons_on_server(self, media, jellyfin_id: str) -> set[int]:
        """Seasons whose every aired episode is in Jellyfin."""
        if not self.jellyfin or not hasattr(self.jellyfin, "list_series_episodes"):
            return set()
        remote = await self.jellyfin.list_series_episodes(jellyfin_id)
        present: dict[int, set[int]] = {}
        for item in remote:
            present.setdefault(item["ParentIndexNumber"], set()).add(item["IndexNumber"])
        today = datetime.now(timezone.utc).date().isoformat()
        expected: dict[int, set[int]] = {}
        for episode in await self.store.list_episodes(media.id):
            if episode.get("air_date") and episode["air_date"] > today:
                continue
            expected.setdefault(episode["season_number"], set()).add(episode["episode_number"])
        complete = set()
        for season_number, numbers in present.items():
            wanted = expected.get(season_number)
            if numbers and (not wanted or wanted <= numbers):
                complete.add(season_number)
        return complete

    async def _release_season_rentals(self, media, jellyfin_id: str, available_at: datetime) -> None:
        pending = [
            rental for rental in await self.store.list_rentals_for_media(media.id)
            if rental.rental_scope == "season" and rental.status in {"requested", "downloading"}
        ]
        if not pending:
            return
        try:
            complete = await self.seasons_on_server(media, jellyfin_id)
        except Exception as error:
            logger.warning("[jellyfin-sync] Season check failed for %s: %s", media.id, error)
            return
        ready = sorted({rental.season_number for rental in pending if rental.season_number in complete})
        await self.store.mark_season_rentals_available(
            media.id, ready, available_at, available_at + timedelta(days=21),
        )

    async def sync_media(
        self, media_id: str, *, jellyfin_items=None, arr_items=None, queue_items=None,
    ) -> Optional[Availability]:
        media = await self.store.fetch_one(media_id)
        if not media or not media.tmdb_id:
            return None
        provider = "sonarr" if media.type == "Série" else "radarr"
        arr = self.sonarr if provider == "sonarr" else self.radarr
        try:
            jellyfin_item, jellyfin_error = await self._find_jellyfin_match(media, jellyfin_items)
            remote = None
            if arr is not None:
                if arr_items is None:
                    arr_items = await self._arr_library(arr, provider == "sonarr")
                remote = next((item for item in arr_items if item.get("tmdbId") == media.tmdb_id), None)
            if jellyfin_item:
                return await self._save_jellyfin_availability(media, provider, jellyfin_item, remote)
            if arr is None or not remote:
                current = await self.store.get_availability(media_id)
                if current and jellyfin_error:
                    return await self.store.upsert_availability(current.model_copy(update={"last_error": jellyfin_error}))
                if (
                    current
                    and arr is not None
                    and not remote
                    and current.state in {"requested", "searching", "downloading", "imported", "available"}
                    and current.last_synced_at
                    and datetime.now(timezone.utc) - current.last_synced_at >= STALE_REQUEST_GRACE
                ):
                    return await self.store.upsert_availability(current.model_copy(update={
                        "arr_id": None,
                        "jellyfin_id": None,
                        "state": "error",
                        "progress_percent": None,
                        "last_error": "Demande absente de Radarr et Jellyfin",
                        "last_synced_at": datetime.now(timezone.utc),
                    }))
                return current
            queue_id_key = "seriesId" if provider == "sonarr" else "movieId"
            if queue_items is None:
                queue_items = await arr.list_queue()
            queue_item = next((item for item in queue_items if item.get(queue_id_key) == remote.get("id")), None)
            progress_percent = None
            last_error = None
            if queue_item and queue_item.get("errorMessage"):
                state = "error"
                last_error = str(queue_item["errorMessage"])
            elif queue_item and isinstance(queue_item.get("size"), (int, float)) and queue_item["size"] > 0:
                progress_percent = round((1 - queue_item.get("sizeleft", queue_item["size"]) / queue_item["size"]) * 100)
                state = "downloading"
            elif queue_item:
                state = "searching"
            else:
                state = "imported" if remote.get("hasFile") else "requested"
            availability = Availability(
                media_id=media.id, provider=provider, arr_id=remote.get("id"),
                state=state, progress_percent=progress_percent, last_error=jellyfin_error or last_error,
                last_synced_at=datetime.now(timezone.utc),
            )
            if availability.arr_id is not None:
                await self.store.clear_arr_id_conflict(provider, availability.arr_id, media.id)
            saved = await self.store.upsert_availability(availability)
            if remote.get("hasFile"):
                await self.store.update(media.id, {"support": "Serveur"})
            return saved
        except Exception as error:
            logger.warning("[jellyfin-sync] Media sync failed for %s: %s", media_id, error)
            current = await self.store.get_availability(media_id)
            if current:
                return await self.store.upsert_availability(current.model_copy(update={
                    "last_error": "Synchronisation indisponible",
                }))
            return None

    async def playback_url(self, media_id: str) -> Optional[str]:
        availability = await self.store.get_availability(media_id)
        if availability and availability.jellyfin_id and self.jellyfin:
            return self.jellyfin.playback_url(availability.jellyfin_id)
        return None

    async def playback_manifest(
        self, media_id: str, season_number: Optional[int] = None,
        episode_number: Optional[int] = None,
    ) -> Optional[dict[str, str]]:
        availability = await self.store.get_availability(media_id)
        if availability and availability.jellyfin_id and self.jellyfin:
            item_id = availability.jellyfin_id
            if season_number is not None and episode_number is not None:
                episode = await self.jellyfin.find_episode(
                    item_id, season_number, episode_number,
                )
                if not episode:
                    return None
                item_id = str(episode["Id"])
            return {
                "item_id": item_id,
                "url": self.jellyfin.playback_manifest_url(item_id),
            }
        return None

    async def playback_options(
        self, media_id: str, season_number: Optional[int] = None,
        episode_number: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        availability = await self.store.get_availability(media_id)
        if not availability or not availability.jellyfin_id or not self.jellyfin:
            return None
        item_id = availability.jellyfin_id
        if season_number is not None and episode_number is not None:
            episode = await self.jellyfin.find_episode(item_id, season_number, episode_number)
            if not episode:
                return None
            item_id = str(episode["Id"])
        return await self.jellyfin.playback_options(item_id)

    async def playback_resource(
        self, media_id: str, resource_path: str, query: dict[str, str],
        season_number: Optional[int] = None, episode_number: Optional[int] = None,
    ):
        availability = await self.store.get_availability(media_id)
        if not availability or not availability.jellyfin_id or not self.jellyfin:
            return None
        item_id = availability.jellyfin_id
        if season_number is not None and episode_number is not None:
            episode = await self.jellyfin.find_episode(item_id, season_number, episode_number)
            if not episode:
                return None
            item_id = str(episode["Id"])
        return await self.jellyfin.fetch_playback_resource(item_id, resource_path, query)

    async def _enrich_media(self, media, media_type: str, tmdb):
        complete = media.cover_url and media.synopsis and media.backdrop_url
        enrich_key = (str(getattr(self.store, "db_path", "")), media.id)
        if not tmdb or not media.tmdb_id or complete or enrich_key in _ENRICHED_MEDIA_IDS:
            return media
        _ENRICHED_MEDIA_IDS.add(enrich_key)
        try:
            details = await tmdb.get_details(media.tmdb_id, is_series=media_type == "Série")
            if details:
                updates = {
                    "cover_url": media.cover_url or tmdb.get_poster_url(details),
                    "backdrop_url": media.backdrop_url or tmdb.get_backdrop_url(details),
                    "synopsis": media.synopsis or details.get("overview") or None,
                    "director": media.director or tmdb.get_director(details),
                    "categories": media.categories or tmdb.get_genres(details),
                    "cast": media.cast or tmdb.get_cast(details, limit=5),
                    "release_date": media.release_date or details.get("release_date") or details.get("first_air_date") or None,
                    "tmdb_ok": True,
                }
                await self.store.update(media.id, {key: value for key, value in updates.items() if value is not None})
                return await self.store.fetch_one(media.id) or media
        except Exception:
            pass
        return media

    async def import_existing_libraries(self) -> dict[str, int]:
        """Link already-managed Arr items to local TMDB-linked records."""
        medias = await self.store.fetch_all()
        try:
            tmdb = TMDBClient()
        except ValueError:
            tmdb = None
        linked = 0
        created = 0
        # Doublons possibles (même TMDB) : on garde la fiche déjà liée à l'élément Radarr/Sonarr,
        # sinon l'unicité (provider, arr_id) casse et bloque toute la synchro.
        linked_by_arr = {
            (availability.provider, availability.arr_id): availability.media_id
            for availability in await self.store.list_availabilities()
            if availability.arr_id is not None
        }
        for provider, client, media_type in (
            ("radarr", self.radarr, "Film"),
            ("sonarr", self.sonarr, "Série"),
        ):
            if client is None:
                continue
            for remote in await self._arr_library(client, media_type == "Série", tmdb):
                tmdb_id = remote.get("tmdbId")
                if not tmdb_id:
                    continue
                owner_id = linked_by_arr.get((provider, remote.get("id")))
                media = next((item for item in medias if item.id == owner_id), None) or next(
                    (item for item in medias if item.type == media_type and item.tmdb_id == tmdb_id), None,
                )
                try:
                    if not media:
                        title = remote.get("title") or remote.get("sortTitle") or "Sans titre"
                        media = await self.store.create({
                            "title": title, "type": media_type, "tmdb_id": tmdb_id,
                            "tmdb_ok": bool(tmdb_id), "status": "À regarder",
                        })
                        medias.append(media)
                        created += 1
                    media = await self._enrich_media(media, media_type, tmdb)
                    await ensure_series_episodes(self.store, tmdb, media)
                    current = await self.store.get_availability(media.id)
                    if (remote.get("hasFile") and current and current.jellyfin_id
                            and current.arr_id == remote.get("id")):
                        # Déjà prêt dans Jellyfin : ne pas repasser par « imported » à chaque cycle.
                        linked += 1
                        continue
                    await self.store.upsert_availability(Availability(
                        media_id=media.id, provider=provider, arr_id=remote.get("id"),
                        state="imported" if remote.get("hasFile") else "requested",
                        last_synced_at=datetime.now(timezone.utc),
                    ))
                except Exception:
                    # Un élément en erreur ne doit pas empêcher les autres (ni l'étape Jellyfin) de se synchroniser.
                    logger.exception("[media-sync] Import impossible pour %s %s", provider, remote.get("id"))
                    continue
                linked += 1
        if self.jellyfin and hasattr(self.jellyfin, "list_library"):
            try:
                jellyfin_items = await self._jellyfin_library(tmdb)
            except Exception as error:
                logger.warning("[jellyfin-sync] Library import failed: %s", error)
                jellyfin_items = []
            for item in jellyfin_items:
                tmdb_id = item.get("tmdb_id")
                media_type = item.get("media_type")
                if not tmdb_id or media_type not in {"Film", "Série"}:
                    continue
                media = next((entry for entry in medias if entry.type == media_type and entry.tmdb_id == tmdb_id), None)
                if not media:
                    media = await self.store.create({
                        "title": item.get("title") or "Sans titre", "type": media_type,
                        "tmdb_id": tmdb_id, "tmdb_ok": True, "status": "À regarder",
                    })
                    medias.append(media)
                    created += 1
                media = await self._enrich_media(media, media_type, tmdb)
                await ensure_series_episodes(self.store, tmdb, media)
                await self._save_jellyfin_availability(
                    media, "sonarr" if media_type == "Série" else "radarr", item,
                )
                linked += 1
        return {"linked": linked, "created": created}

    async def sync_all(self) -> dict[str, int]:
        await self.import_existing_libraries()
        jellyfin_items = None
        if self.jellyfin and hasattr(self.jellyfin, "list_library"):
            try:
                jellyfin_items = await self._jellyfin_library()
            except Exception as error:
                logger.warning("[jellyfin-sync] Library snapshot failed: %s", error)
                jellyfin_items = None
        arr_items_by_provider: dict[str, list[dict[str, Any]]] = {}
        queue_items_by_provider: dict[str, list[dict[str, Any]]] = {}
        for provider, client in (("radarr", self.radarr), ("sonarr", self.sonarr)):
            if client is None:
                continue
            arr_items_by_provider[provider] = await self._arr_library(client, provider == "sonarr")
            queue_items_by_provider[provider] = await client.list_queue()
        synced = 0
        for media in await self.store.fetch_all():
            if media.tmdb_id and media.type in {"Film", "Série"}:
                provider = "sonarr" if media.type != "Film" else "radarr"
                if await self.sync_media(
                    media.id,
                    jellyfin_items=jellyfin_items,
                    arr_items=arr_items_by_provider.get("sonarr" if media.type != "Film" else "radarr"),
                    queue_items=queue_items_by_provider.get("sonarr" if media.type != "Film" else "radarr"),
                ):
                    synced += 1
        return {"synced": synced}

    async def activity(self) -> dict[str, list[dict[str, Any]]]:
        disks: list[dict[str, Any]] = []
        for provider, client in (("radarr", self.radarr), ("sonarr", self.sonarr)):
            if client is None or not hasattr(client, "disk_space"):
                continue
            try:
                for disk in await client.disk_space():
                    disks.append({"provider": provider, **disk})
            except Exception:
                continue
        medias = {media.id: media for media in await self.store.fetch_all()}
        items = []
        for availability in await self.store.list_availabilities():
            item = availability.model_dump(mode="json")
            media = medias.get(availability.media_id)
            if media:
                item.update({"title": media.title, "media_type": media.type, "tmdb_id": media.tmdb_id})
            items.append(item)
        return {
            "items": items,
            "disks": disks,
        }

    async def storage_status(self) -> dict[str, Any]:
        activity = await self.activity()
        disks = activity["disks"]
        data_disks = [
            disk for disk in disks
            if str(disk.get("path", "")).startswith("/data")
        ]
        relevant_disks = data_disks or disks
        free_values = [
            int(disk["freeSpace"])
            for disk in relevant_disks
            if isinstance(disk.get("freeSpace"), (int, float))
        ]
        min_free_bytes = min(free_values) if free_values else None
        temporary_bytes = await self.store.active_temporary_bytes()
        return {
            "min_free_bytes": min_free_bytes,
            "min_free_gb": round(min_free_bytes / 1024**3, 2) if min_free_bytes is not None else None,
            "temporary_bytes": temporary_bytes,
            "temporary_gb": round(temporary_bytes / 1024**3, 2),
            "min_free_threshold_bytes": Config.min_free_bytes(),
            "min_free_threshold_gb": Config.MIN_FREE_GB,
            "temporary_max_bytes": Config.temporary_max_bytes(),
            "temporary_max_gb": Config.TEMPORARY_MAX_GB,
            "low_space": min_free_bytes is not None and min_free_bytes < Config.min_free_bytes(),
            "temporary_quota_reached": temporary_bytes >= Config.temporary_max_bytes(),
        }

    @staticmethod
    def _remote_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None

    async def storage_candidates(self, *, now: Optional[datetime] = None) -> list[StorageCandidate]:
        """List imported Radarr films that an administrator may review for deletion."""
        if self.radarr is None:
            raise RuntimeError("Radarr n'est pas configuré")
        now = now or datetime.now(timezone.utc)
        remotes = await self.radarr.list_library()
        medias = {
            media.tmdb_id: media
            for media in await self.store.fetch_all()
            if media.type == "Film" and media.tmdb_id
        }
        context = await self.store.storage_context(now - timedelta(days=30))
        candidates = []
        for remote in remotes:
            tmdb_id = remote.get("tmdbId")
            media = medias.get(tmdb_id)
            size_bytes = remote.get("sizeOnDisk")
            if not media or not remote.get("id") or not remote.get("hasFile"):
                continue
            if not isinstance(size_bytes, (int, float)) or size_bytes <= 0:
                continue
            added_at = self._remote_datetime(remote.get("added")) or media.created_at
            reasons = []
            if media.id in context["favorite_media_ids"]:
                reasons.append("favorite")
            has_active_rental = media.id in context["rental_media_ids"]
            if has_active_rental:
                reasons.append("active_rental")
            if added_at and added_at >= now - timedelta(days=14):
                reasons.append("recently_added")
            last_played_at = context["last_playback"].get(media.id)
            if media.id in context["recent_playback"]:
                reasons.append("recently_watched")
            if media.id in context["protected_media_ids"]:
                reasons.append("manual")
            candidates.append(StorageCandidate(
                media_id=media.id,
                title=media.title,
                tmdb_id=media.tmdb_id,
                radarr_id=int(remote["id"]),
                path=remote.get("path"),
                size_bytes=int(size_bytes),
                added_at=added_at,
                last_played_at=last_played_at,
                is_favorite=media.id in context["favorite_media_ids"],
                has_active_rental=has_active_rental,
                rental_expired=media.id in context.get("expired_rental_media_ids", set()),
                protected=bool(HARD_STORAGE_PROTECTION_REASONS.intersection(reasons)),
                protection_reasons=reasons,
            ))
        return sorted(candidates, key=lambda item: (-item.size_bytes, item.title.lower()))

    async def set_storage_protection(self, media_id: str, protected: bool) -> bool:
        return await self.store.set_storage_protection(media_id, protected)

    async def cancel_pending_movie(self, media_id: str) -> bool:
        """Remove a queued Radarr movie after its last rental has been revoked."""
        availability = await self.store.get_availability(media_id)
        if not availability or availability.provider != "radarr" or not availability.arr_id or not self.radarr:
            return False
        await self.radarr.delete_movie(availability.arr_id, delete_files=True)
        await self.store.upsert_availability(availability.model_copy(update={
            "arr_id": None, "jellyfin_id": None, "state": "error", "progress_percent": None,
            "last_error": "Demande de location révoquée par l'administrateur",
            "last_synced_at": datetime.now(timezone.utc),
        }))
        try:
            await self.sync_media(media_id, jellyfin_items=[])
        except Exception:
            # Radarr has already removed the request; the next server sync can repair Jellyfin metadata.
            pass
        return True

    async def delete_expired_rentals(self, admin_user_id: str) -> dict[str, Any]:
        """Delete every unprotected film whose only rentals have expired."""
        targets = [
            item for item in await self.storage_candidates()
            if item.rental_expired and not item.protected
        ]
        deleted, failed, freed_bytes = [], [], 0
        for candidate in targets:
            try:
                result = await self.delete_storage_candidate(candidate.media_id, admin_user_id)
            except (LookupError, PermissionError, RuntimeError) as error:
                failed.append({"media_id": candidate.media_id, "title": candidate.title, "error": str(error)})
                continue
            deleted.append({"media_id": candidate.media_id, "title": candidate.title})
            freed_bytes += int(result.get("freed_bytes") or candidate.size_bytes)
        return {"deleted": deleted, "failed": failed, "freed_bytes": freed_bytes}

    async def delete_storage_candidate(
        self, media_id: str, admin_user_id: str, *, allow_protected: bool = False,
    ) -> dict[str, Any]:
        candidates = await self.storage_candidates()
        candidate = next((item for item in candidates if item.media_id == media_id), None)
        if candidate is None:
            raise LookupError("Film absent de Radarr ou non éligible à la suppression")
        if candidate.protected and not allow_protected:
            raise PermissionError("Ce film est protégé et ne peut pas être supprimé")
        if self.radarr is None:
            raise RuntimeError("Radarr n'est pas configuré")

        await self.radarr.delete_movie(candidate.radarr_id, delete_files=True)
        now = datetime.now(timezone.utc)
        current = await self.store.get_availability(media_id)
        availability = Availability(
            media_id=media_id,
            provider="radarr",
            arr_id=None,
            jellyfin_id=None,
            state="error",
            root_folder=current.root_folder if current else None,
            quality_profile_id=current.quality_profile_id if current else None,
            language_profile_id=current.language_profile_id if current else None,
            last_error="Film supprimé du stockage par l'administrateur",
            last_synced_at=now,
        )
        await self.store.upsert_availability(availability)

        sync_warning = None
        try:
            # Use an empty snapshot so an eventual Jellyfin index refresh cannot
            # immediately turn the fiche back into a playable item.
            await self.sync_media(media_id, jellyfin_items=[])
        except Exception as error:  # deletion already succeeded; report the warning
            sync_warning = str(error)

        await self.store.record_storage_cleanup({
            "admin_user_id": admin_user_id,
            "media_id": media_id,
            "media_title": candidate.title,
            "size_bytes": candidate.size_bytes,
            "deleted_at": now,
            "status": "deleted",
            "error": sync_warning,
        })
        return {
            "media_id": media_id,
            "title": candidate.title,
            "freed_bytes": candidate.size_bytes,
            "availability": "error",
            "synced": sync_warning is None,
            "sync_warning": sync_warning,
        }

    async def sync_playback(self, backstage_user_id: str, jellyfin_user_id: str) -> dict[str, int]:
        if not self.jellyfin:
            raise RuntimeError("Jellyfin n'est pas configuré")
        remote_items = await self.jellyfin.user_playback(jellyfin_user_id)
        synced = 0
        for item in remote_items:
            media_id, episode_id = await self.store.resolve_playback_item(item)
            progress = PlaybackProgress(
                backstage_user_id=backstage_user_id,
                jellyfin_id=item["jellyfin_id"],
                media_id=media_id,
                episode_id=episode_id,
                title=item["title"],
                series_title=item.get("series_title"),
                season_number=item.get("season_number"),
                episode_number=item.get("episode_number"),
                position_ticks=item.get("position_ticks", 0),
                runtime_ticks=item.get("runtime_ticks", 0),
                percent=min(100, max(0, float(item.get("percent", 0)))),
                played=bool(item.get("played")) or float(item.get("percent", 0)) >= 95,
                last_played_at=item.get("last_played_at"),
            )
            await self.store.upsert_playback(progress)
            if media_id and progress.position_ticks > 0:
                first_played_at = datetime.now(timezone.utc)
                await self.store.mark_rental_first_played(
                    backstage_user_id, media_id, first_played_at, first_played_at + timedelta(days=7),
                )
            synced += 1
        return {"synced": synced}

    async def playback_summary(self, backstage_user_id: str) -> dict[str, Any]:
        return {
            "resume": await self.store.list_resume_progress(backstage_user_id),
            "next_episodes": await self.store.list_next_episodes(backstage_user_id),
            "recently_completed": await self.store.list_recently_completed(backstage_user_id),
            "last_synced_at": await self.store.last_playback_sync(backstage_user_id),
        }
