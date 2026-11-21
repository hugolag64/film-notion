"""Server-side Jellyfin lookup; no API key reaches the browser."""
import re
import time
from typing import Any, Optional
from pathlib import PurePosixPath
from urllib.parse import quote, urlencode

import httpx

from backend.core import http

CLIENT_NAME = "Backstage"
DEVICE_NAME = "Backstage"
DEVICE_ID = "backstage"
CLIENT_VERSION = "1.0.0"
_EPISODE_CACHE_TTL_SEC = 900
_episode_cache: dict[tuple[str, str, int, int], tuple[float, dict[str, Any]]] = {}


def _quote_auth_value(value: str) -> str:
    """Values of the MediaBrowser scheme are double-quoted; strip what would break it."""
    return re.sub(r'["\\\x00-\x1f]', "", str(value))


class JellyfinClient:
    def __init__(
        self, base_url: str, api_key: str, client: Optional[httpx.AsyncClient] = None,
        *, server_id: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = client
        self.server_id = server_id

    def _auth_headers(self) -> dict[str, str]:
        """Modern Jellyfin authentication; the API key never leaves the backend."""
        fields = {
            "Client": CLIENT_NAME,
            "Device": DEVICE_NAME,
            "DeviceId": DEVICE_ID,
            "Version": CLIENT_VERSION,
            "Token": self.api_key,
        }
        value = ", ".join(f'{key}="{_quote_auth_value(item)}"' for key, item in fields.items())
        return {"Authorization": f"MediaBrowser {value}"}

    async def list_users(self) -> list[dict[str, Any]]:
        client = self.client or http.get_client()
        response = await client.get(
            f"{self.base_url}/Users",
            headers=self._auth_headers(),
            timeout=10.0,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except (TypeError, ValueError) as error:
            raise ValueError("invalid Jellyfin users response") from error
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("Users"), list):
            items = payload["Users"]
        else:
            raise ValueError("invalid Jellyfin users response")

        users = []
        for item in items:
            if not isinstance(item, dict) or not item.get("Id"):
                raise ValueError("invalid Jellyfin users response")
            policy = item.get("Policy") or {}
            if not isinstance(policy, dict):
                raise ValueError("invalid Jellyfin users response")
            users.append({
                "id": str(item["Id"]),
                "name": str(item.get("Name") or item["Id"]),
                "is_admin": bool(policy.get("IsAdministrator", False)),
            })
        return users

    @staticmethod
    def _items_from_payload(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("Items"), list):
            items = payload["Items"]
        else:
            raise ValueError("invalid Jellyfin playback response")
        return [item for item in items if isinstance(item, dict) and item.get("Id")]

    async def user_playback(self, user_id: str) -> list[dict[str, Any]]:
        client = self.client or http.get_client()
        fields = "ProviderIds,UserData,SeriesName,SeriesId,IndexNumber,ParentIndexNumber"
        requests = (
            (f"{self.base_url}/Users/{quote(user_id, safe='')}/Items", {
                "Recursive": "true", "IsResumable": "true", "Fields": fields,
            }),
            (f"{self.base_url}/Users/{quote(user_id, safe='')}/Items/Latest", {
                "Fields": fields, "Limit": "50",
            }),
        )
        normalized: dict[str, dict[str, Any]] = {}
        for url, params in requests:
            response = await client.get(
                url,
                headers=self._auth_headers(),
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            items = self._items_from_payload(response.json())
            for item in items:
                user_data = item.get("UserData") or {}
                runtime = int(item.get("RunTimeTicks") or 0)
                position = int(user_data.get("PlaybackPositionTicks") or 0)
                percent = round(position * 100 / runtime, 2) if runtime else 0
                provider_ids = item.get("ProviderIds") or {}
                normalized[str(item["Id"])] = {
                    "jellyfin_id": str(item["Id"]),
                    "tmdb_id": int(provider_ids["Tmdb"]) if str(provider_ids.get("Tmdb", "")).isdigit() else None,
                    "title": str(item.get("Name") or item["Id"]),
                    "item_type": item.get("Type"),
                    "series_title": item.get("SeriesName"),
                    "series_jellyfin_id": item.get("SeriesId"),
                    "season_number": item.get("ParentIndexNumber"),
                    "episode_number": item.get("IndexNumber"),
                    "position_ticks": position,
                    "runtime_ticks": runtime,
                    "percent": percent,
                    "played": bool(user_data.get("Played")),
                    "last_played_at": user_data.get("LastPlayedDate"),
                }
        return list(normalized.values())

    async def list_library(self) -> list[dict[str, Any]]:
        """Return TMDB-linked movies and series present in Jellyfin."""
        client = self.client or http.get_client()
        limit = 1000
        start_index = 0
        normalized: list[dict[str, Any]] = []

        while True:
            response = await client.get(
                f"{self.base_url}/Items",
                headers=self._auth_headers(),
                params={
                    "IncludeItemTypes": "Movie,Series",
                    "Recursive": "true",
                    "Fields": "ProviderIds,Overview,ProductionYear,ImageTags,BackdropImageTags",
                    "Limit": limit,
                    "StartIndex": start_index,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("Items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise ValueError("invalid Jellyfin library response")

            for item in items:
                if not isinstance(item, dict) or not item.get("Id"):
                    continue
                if item.get("Type") not in {"Movie", "Series"}:
                    continue
                provider_ids = item.get("ProviderIds") or {}
                raw_tmdb_id = provider_ids.get("Tmdb")
                if not str(raw_tmdb_id or "").isdigit():
                    continue
                normalized.append({
                    "jellyfin_id": str(item["Id"]),
                    "tmdb_id": int(raw_tmdb_id),
                    "title": str(item.get("Name") or item["Id"]),
                    "media_type": "Série" if item.get("Type") == "Series" else "Film",
                    "year": item.get("ProductionYear"),
                    "overview": item.get("Overview") or None,
                    "poster_tag": self._image_tag(item.get("ImageTags"), "Primary"),
                    "backdrop_tag": self._backdrop_tag(item.get("BackdropImageTags")),
                })

            if len(items) < limit:
                break
            start_index += len(items)

        return normalized

    @staticmethod
    def _image_tag(value: Any, key: str) -> Optional[str]:
        return value.get(key) if isinstance(value, dict) else None

    @staticmethod
    def _backdrop_tag(value: Any) -> Optional[str]:
        if isinstance(value, dict):
            return value.get("Backdrop")
        if isinstance(value, list):
            return next((tag for tag in value if isinstance(tag, str) and tag), None)
        return None

    async def find_episode(
        self, series_id: str, season_number: int, episode_number: int,
    ) -> Optional[dict[str, Any]]:
        """Find a Jellyfin episode by its season and episode numbers."""
        cache_key = (self.base_url, series_id, season_number, episode_number)
        cached = _episode_cache.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        client = self.client or http.get_client()
        response = await client.get(
            f"{self.base_url}/Shows/{quote(series_id, safe='')}/Episodes",
            headers=self._auth_headers(),
            params={"season": season_number, "Fields": "ProviderIds"},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("Items", []) if isinstance(payload, dict) else []
        if not isinstance(items, list):
            raise ValueError("invalid Jellyfin episodes response")
        episode = next((
            item for item in items
            if isinstance(item, dict)
            and item.get("ParentIndexNumber") == season_number
            and item.get("IndexNumber") == episode_number
            and item.get("Id")
        ), None)
        if episode:
            _episode_cache[cache_key] = (time.monotonic() + _EPISODE_CACHE_TTL_SEC, episode)
        return episode

    async def list_series_episodes(self, series_id: str) -> list[dict[str, Any]]:
        """Return the episodes Jellyfin actually has for a series."""
        client = self.client or http.get_client()
        limit = 1000
        start_index = 0
        episodes: list[dict[str, Any]] = []
        while True:
            response = await client.get(
                f"{self.base_url}/Shows/{quote(series_id, safe='')}/Episodes",
                headers=self._auth_headers(),
                params={"Fields": "ProviderIds", "Limit": limit, "StartIndex": start_index},
                timeout=10.0,
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("Items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                raise ValueError("invalid Jellyfin episodes response")
            valid_items = [
                item for item in items
                if isinstance(item, dict)
                and item.get("Id")
                and isinstance(item.get("ParentIndexNumber"), int)
                and isinstance(item.get("IndexNumber"), int)
            ]
            episodes.extend(valid_items)
            expires_at = time.monotonic() + _EPISODE_CACHE_TTL_SEC
            for item in valid_items:
                key = (
                    self.base_url, series_id,
                    item["ParentIndexNumber"], item["IndexNumber"],
                )
                _episode_cache[key] = (expires_at, item)
            if len(items) < limit:
                break
            start_index += len(items)
        return episodes

    async def playback_options(self, item_id: str) -> dict[str, Any]:
        """Return audio/subtitle tracks and the source id Jellyfin uses for playback."""
        client = self.client or http.get_client()
        response = await client.get(
            f"{self.base_url}/Items/{quote(item_id, safe='')}/PlaybackInfo",
            headers=self._auth_headers(),
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        sources = payload.get("MediaSources", []) if isinstance(payload, dict) else []
        if not isinstance(sources, list) or not sources:
            raise ValueError("Jellyfin n'a renvoyé aucune source de lecture")
        source = next((entry for entry in sources if isinstance(entry, dict)), None)
        if source is None:
            raise ValueError("Sources de lecture Jellyfin invalides")
        streams = source.get("MediaStreams", [])
        if not isinstance(streams, list):
            streams = []

        def normalize_track(track: Any) -> Optional[dict[str, Any]]:
            if not isinstance(track, dict) or not isinstance(track.get("Index"), int):
                return None
            language = str(track.get("Language") or "").strip()
            title = str(track.get("DisplayTitle") or track.get("Title") or "").strip()
            details = " · ".join(part for part in (language, title, track.get("Codec")) if part)
            return {
                "index": track["Index"],
                "label": details or f"Piste {track['Index'] + 1}",
                "language": language or None,
                "is_default": bool(track.get("IsDefault")),
            }

        audio = [normalize_track(track) for track in streams if isinstance(track, dict) and track.get("Type") == "Audio"]
        subtitles = [normalize_track(track) for track in streams if isinstance(track, dict) and track.get("Type") == "Subtitle"]
        audio = [track for track in audio if track]
        subtitles = [track for track in subtitles if track]
        return {
            "media_source_id": str(source.get("Id") or item_id),
            "audio_tracks": audio,
            "subtitle_tracks": subtitles,
            "default_audio_index": source.get("DefaultAudioStreamIndex"),
            "default_subtitle_index": source.get("DefaultSubtitleStreamIndex"),
        }

    async def find_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[dict[str, Any]]:
        item_type = "Series" if media_type == "Série" else "Movie"
        client = self.client or http.get_client()
        limit = 1000
        start_index = 0
        try:
            while True:
                response = await client.get(
                    f"{self.base_url}/Items",
                    headers=self._auth_headers(),
                    params={
                        "IncludeItemTypes": item_type,
                        "Recursive": "true",
                        "Fields": "ProviderIds",
                        "Limit": limit,
                        "StartIndex": start_index,
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                items = response.json().get("Items", [])
                for item in items:
                    if item.get("Type") == item_type and str(item.get("ProviderIds", {}).get("Tmdb")) == str(tmdb_id):
                        return item
                if len(items) < limit:
                    break
                start_index += len(items)
        except (httpx.HTTPError, ValueError):
            return None
        return None

    def playback_url(self, item_id: str, *, base_url: Optional[str] = None) -> str:
        web_base_url = (base_url or self.base_url).rstrip("/")
        url = f"{web_base_url}/web/index.html#/details?id={quote(item_id, safe='')}"
        if self.server_id:
            url += f"&serverId={quote(self.server_id, safe='')}"
        return url

    def playback_manifest_url(self, item_id: str) -> str:
        params = urlencode(self.playback_manifest_params(item_id))
        return f"{self.base_url}/Videos/{quote(item_id, safe='')}/master.m3u8?{params}"

    @staticmethod
    def playback_manifest_params(
        item_id: str, *, media_source_id: Optional[str] = None,
        audio_stream_index: Optional[int] = None,
        subtitle_stream_index: Optional[int] = None,
        start_time_ticks: Optional[int] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "VideoCodec": "h264",
            "AudioCodec": "aac",
            "Container": "ts",
            "TranscodingContainer": "ts",
            "TranscodingProtocol": "hls",
            "MaxWidth": "3840",
            "MaxHeight": "2160",
            "VideoBitrate": "40000000",
            "MaxStreamingBitrate": "45000000",
            "EnableAdaptiveBitrateStreaming": "true",
            "MediaSourceId": media_source_id or item_id,
        }
        if audio_stream_index is not None:
            params["AudioStreamIndex"] = audio_stream_index
        if subtitle_stream_index is not None:
            params["SubtitleStreamIndex"] = subtitle_stream_index
            params["SubtitleMethod"] = "Encode" if subtitle_stream_index >= 0 else "External"
        if start_time_ticks is not None and start_time_ticks > 0:
            params["StartTimeTicks"] = start_time_ticks
        return params

    async def fetch_playback_resource(
        self, item_id: str, resource_path: str, query: Optional[dict[str, str]] = None,
    ) -> httpx.Response:
        normalized = PurePosixPath(resource_path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("Chemin de lecture invalide")
        url = f"{self.base_url}/Videos/{quote(item_id, safe='')}/{quote(str(normalized), safe='/')}"
        client = self.client or http.get_client()
        response = await client.get(
            url, headers=self._auth_headers(), params=query or {}, timeout=60.0,
        )
        response.raise_for_status()
        return response
