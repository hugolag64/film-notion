"""Shared models for the local media-server integration."""
from datetime import datetime, timedelta
from datetime import timezone
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.core.playback import PlaybackProgress
from backend.config import Config
from backend.core.tmdb import TMDBClient


logger = logging.getLogger(__name__)
STALE_REQUEST_GRACE = timedelta(hours=1)
HARD_STORAGE_PROTECTION_REASONS = {"favorite", "active_rental", "manual"}


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

    async def add(
        self, media, quality_profile_id: Optional[int], root_folder: Optional[str],
        language_profile_id: Optional[int], monitor: str,
    ) -> Availability:
        if not media.tmdb_id:
            raise ValueError("Associez d'abord ce média à TMDB")
        provider = "sonarr" if media.type == "Série" else "radarr"
        if self.seerr:
            remote = await self.seerr.request_media(
                tmdb_id=media.tmdb_id, media_type=media.type,
                quality_profile_id=None, root_folder=None,
                language_profile_id=None, monitor=monitor,
            )
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
                library_items = await self.jellyfin.list_library()
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
        return saved

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
                    arr_items = await arr.list_library()
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

    async def playback_manifest(self, media_id: str) -> Optional[dict[str, str]]:
        availability = await self.store.get_availability(media_id)
        if availability and availability.jellyfin_id and self.jellyfin:
            return {
                "item_id": availability.jellyfin_id,
                "url": self.jellyfin.playback_manifest_url(availability.jellyfin_id),
            }
        return None

    async def playback_resource(self, media_id: str, resource_path: str, query: dict[str, str]):
        availability = await self.store.get_availability(media_id)
        if not availability or not availability.jellyfin_id or not self.jellyfin:
            return None
        return await self.jellyfin.fetch_playback_resource(availability.jellyfin_id, resource_path, query)

    async def _enrich_media(self, media, media_type: str, tmdb):
        if not tmdb or not media.tmdb_id or (media.cover_url and media.synopsis):
            return media
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
        for provider, client, media_type in (
            ("radarr", self.radarr, "Film"),
            ("sonarr", self.sonarr, "Série"),
        ):
            if client is None:
                continue
            for remote in await client.list_library():
                tmdb_id = remote.get("tmdbId")
                media = next((item for item in medias if item.type == media_type and item.tmdb_id == tmdb_id), None)
                if not media:
                    title = remote.get("title") or remote.get("sortTitle") or "Sans titre"
                    media = await self.store.create({
                        "title": title, "type": media_type, "tmdb_id": tmdb_id,
                        "tmdb_ok": bool(tmdb_id), "status": "À regarder",
                    })
                    medias.append(media)
                    created += 1
                media = await self._enrich_media(media, media_type, tmdb)
                await self.store.upsert_availability(Availability(
                    media_id=media.id, provider=provider, arr_id=remote.get("id"),
                    state="imported" if remote.get("hasFile") else "requested",
                    last_synced_at=datetime.now(timezone.utc),
                ))
                linked += 1
        if self.jellyfin and hasattr(self.jellyfin, "list_library"):
            try:
                jellyfin_items = await self.jellyfin.list_library()
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
                jellyfin_items = await self.jellyfin.list_library()
            except Exception as error:
                logger.warning("[jellyfin-sync] Library snapshot failed: %s", error)
                jellyfin_items = None
        arr_items_by_provider: dict[str, list[dict[str, Any]]] = {}
        queue_items_by_provider: dict[str, list[dict[str, Any]]] = {}
        for provider, client in (("radarr", self.radarr), ("sonarr", self.sonarr)):
            if client is None:
                continue
            arr_items_by_provider[provider] = await client.list_library()
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
                protected=bool(HARD_STORAGE_PROTECTION_REASONS.intersection(reasons)),
                protection_reasons=reasons,
            ))
        return sorted(candidates, key=lambda item: (-item.size_bytes, item.title.lower()))

    async def set_storage_protection(self, media_id: str, protected: bool) -> bool:
        return await self.store.set_storage_protection(media_id, protected)

    async def delete_storage_candidate(self, media_id: str, admin_user_id: str) -> dict[str, Any]:
        candidates = await self.storage_candidates()
        candidate = next((item for item in candidates if item.media_id == media_id), None)
        if candidate is None:
            raise LookupError("Film absent de Radarr ou non éligible à la suppression")
        if candidate.protected:
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
