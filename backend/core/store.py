"""Persistance locale des médias (SQLite), remplace Notion comme source de vérité."""
import asyncio
import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.models import Media

_COLUMNS = [
    "id", "title", "original_title", "type", "status", "support", "rating", "release_date",
    "director", "categories", "synopsis", "tags", "review", "tmdb_ok", "tmdb_id", "cover_url",
    "watched_in_cinema", "watched_date", "backdrop_url", "cast", "created_at",
]

_LIST_FIELDS = {"categories", "tags", "cast"}


class MediaStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    original_title TEXT,
                    type TEXT,
                    status TEXT,
                    support TEXT,
                    rating TEXT,
                    release_date TEXT,
                    director TEXT,
                    categories TEXT,
                    synopsis TEXT,
                    tags TEXT,
                    review TEXT,
                    tmdb_ok INTEGER NOT NULL DEFAULT 0,
                    tmdb_id INTEGER,
                    cover_url TEXT,
                    watched_in_cinema INTEGER NOT NULL DEFAULT 0,
                    watched_date TEXT,
                    backdrop_url TEXT,
                    cast TEXT,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episode (
                    id TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    season_number INTEGER NOT NULL,
                    episode_number INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    synopsis TEXT,
                    watched INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(media_id, season_number, episode_number),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            # Migration en douceur si les colonnes n'existent pas encore
            cursor = conn.execute("PRAGMA table_info(media)")
            columns = [column[1] for column in cursor.fetchall()]
            if "watched_in_cinema" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN watched_in_cinema INTEGER NOT NULL DEFAULT 0")
            if "watched_date" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN watched_date TEXT")
            if "backdrop_url" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN backdrop_url TEXT")
            if "cast" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN cast TEXT")
            if "created_at" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN created_at TEXT")
            if "tmdb_id" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN tmdb_id INTEGER")
            if "original_title" not in columns:
                conn.execute("ALTER TABLE media ADD COLUMN original_title TEXT")
            conn.execute("UPDATE media SET created_at = COALESCE(created_at, datetime('now'))")
            episode_columns = [column[1] for column in conn.execute("PRAGMA table_info(episode)").fetchall()]
            if "synopsis" not in episode_columns:
                conn.execute("ALTER TABLE episode ADD COLUMN synopsis TEXT")


    @staticmethod
    def _row_to_media(row: sqlite3.Row) -> Media:
        data = dict(row)
        for field in _LIST_FIELDS:
            data[field] = json.loads(data[field]) if data[field] else []
        data["tmdb_ok"] = bool(data["tmdb_ok"])
        data["watched_in_cinema"] = bool(data.get("watched_in_cinema", 0))
        if data.get("release_date"):
            data["release_date"] = date.fromisoformat(data["release_date"])
        if data.get("created_at"):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return Media(**data)

    @staticmethod
    def _encode(field: str, value: Any) -> Any:
        if field in _LIST_FIELDS:
            return json.dumps(value or [])
        if field == "release_date" and value is not None:
            return value.isoformat() if isinstance(value, date) else value
        if field == "created_at" and value is not None:
            return value.isoformat() if isinstance(value, datetime) else value
        if field in ("tmdb_ok", "watched_in_cinema"):
            return int(bool(value))
        return value

    def _fetch_all_sync(self) -> List[Media]:
        escaped_cols = ", ".join(f'"{col}"' for col in _COLUMNS)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT {escaped_cols} FROM media ORDER BY rowid").fetchall()
        return [self._row_to_media(row) for row in rows]

    def _fetch_one_sync(self, media_id: str) -> Optional[Media]:
        escaped_cols = ", ".join(f'"{col}"' for col in _COLUMNS)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT {escaped_cols} FROM media WHERE id = ?", (media_id,)
            ).fetchone()
        return self._row_to_media(row) if row else None

    def _create_sync(self, fields: Dict[str, Any]) -> Media:
        media_id = fields.get("id") or str(uuid.uuid4())
        values = {col: fields.get(col) for col in _COLUMNS if col != "id"}
        values["id"] = media_id
        values["created_at"] = values["created_at"] or datetime.now(timezone.utc)

        escaped_cols = ", ".join(f'"{col}"' for col in _COLUMNS)
        with sqlite3.connect(self.db_path) as conn:
            placeholders = ", ".join("?" for _ in _COLUMNS)
            conn.execute(
                f"INSERT INTO media ({escaped_cols}) VALUES ({placeholders})",
                [self._encode(col, values[col]) for col in _COLUMNS],
            )
        return self._fetch_one_sync(media_id)

    def _update_sync(self, media_id: str, fields: Dict[str, Any]) -> bool:
        if not fields:
            return self._fetch_one_sync(media_id) is not None
        filtered_fields = {col: fields.get(col) for col in _COLUMNS if col != "id" and col in fields}
        if not filtered_fields:
            return self._fetch_one_sync(media_id) is not None
        set_clause = ", ".join(f'"{col}" = ?' for col in filtered_fields)
        values = [self._encode(col, val) for col, val in filtered_fields.items()]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE media SET {set_clause} WHERE id = ?", [*values, media_id]
            )
            return cursor.rowcount > 0


    def _delete_sync(self, media_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM episode WHERE media_id = ?", (media_id,))
            cursor = conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_episode(row: sqlite3.Row) -> Dict[str, Any]:
        episode = dict(row)
        episode["watched"] = bool(episode["watched"])
        if not episode.get("synopsis"):
            episode.pop("synopsis", None)
        return episode

    @staticmethod
    def _progress_from_rows(media_id: str, rows: List[sqlite3.Row]) -> Dict[str, Any]:
        seasons: Dict[int, Dict[str, Any]] = {}
        watched = 0
        for row in rows:
            season_number = row["season_number"]
            season = seasons.setdefault(season_number, {
                "season_number": season_number,
                "watched": 0,
                "total": 0,
            })
            season["total"] += 1
            if row["watched"]:
                watched += 1
                season["watched"] += 1

        for season in seasons.values():
            season["percentage"] = round(season["watched"] * 100 / season["total"], 2)

        total = len(rows)
        percentage = round(watched * 100 / total, 2) if total else 0
        status = "Terminée" if total and watched == total else "En cours" if watched else "À regarder"
        return {
            "media_id": media_id,
            "status": status,
            "watched": watched,
            "total": total,
            "percentage": percentage,
            "seasons": [seasons[number] for number in sorted(seasons)],
        }

    def _list_episodes_sync(self, media_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT episode.id, episode.media_id, episode.season_number,
                       episode.episode_number, episode.title, episode.synopsis, episode.watched
                FROM episode
                JOIN media ON media.id = episode.media_id
                WHERE episode.media_id = ? AND media.type = 'Série'
                ORDER BY episode.season_number, episode.episode_number
                """,
                (media_id,),
            ).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def _series_progress_sync(self, media_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            media = conn.execute(
                "SELECT id FROM media WHERE id = ? AND type = 'Série'", (media_id,)
            ).fetchone()
            if not media:
                return None
            rows = conn.execute(
                "SELECT season_number, watched FROM episode WHERE media_id = ?",
                (media_id,),
            ).fetchall()
        return self._progress_from_rows(media_id, rows)

    def _recalculate_series_status(self, conn: sqlite3.Connection, media_id: str) -> Dict[str, Any]:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT season_number, watched FROM episode WHERE media_id = ?",
            (media_id,),
        ).fetchall()
        progress = self._progress_from_rows(media_id, rows)
        conn.execute("UPDATE media SET status = ? WHERE id = ?", (progress["status"], media_id))
        return progress

    def _create_episodes_sync(self, media_id: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            media = conn.execute(
                "SELECT id FROM media WHERE id = ? AND type = 'Série'", (media_id,)
            ).fetchone()
            if not media:
                return []
            for episode in episodes:
                conn.execute(
                    """
                    INSERT INTO episode (id, media_id, season_number, episode_number, title, synopsis, watched)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode.get("id") or str(uuid.uuid4()),
                        media_id,
                        episode["season_number"],
                        episode["episode_number"],
                        episode["title"],
                        episode.get("synopsis"),
                        int(bool(episode.get("watched", False))),
                    ),
                )
            self._recalculate_series_status(conn, media_id)
        return self._list_episodes_sync(media_id)

    def _upsert_episodes_sync(self, media_id: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Refresh TMDB episode metadata without ever resetting local watch history."""
        with sqlite3.connect(self.db_path) as conn:
            media = conn.execute(
                "SELECT id FROM media WHERE id = ? AND type = 'Série'", (media_id,)
            ).fetchone()
            if not media:
                return []
            for episode in episodes:
                conn.execute(
                    """
                    INSERT INTO episode (id, media_id, season_number, episode_number, title, synopsis, watched)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(media_id, season_number, episode_number) DO UPDATE SET
                        title = excluded.title,
                        synopsis = excluded.synopsis
                    """,
                    (
                        str(uuid.uuid4()), media_id, episode["season_number"],
                        episode["episode_number"], episode["title"], episode.get("synopsis"),
                    ),
                )
            self._recalculate_series_status(conn, media_id)
        return self._list_episodes_sync(media_id)

    def _set_episode_watched_sync(self, episode_id: str, watched: bool) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            episode = conn.execute(
                """
                SELECT episode.media_id
                FROM episode
                JOIN media ON media.id = episode.media_id
                WHERE episode.id = ? AND media.type = 'Série'
                """,
                (episode_id,),
            ).fetchone()
            if not episode:
                return None
            conn.execute("UPDATE episode SET watched = ? WHERE id = ?", (int(watched), episode_id))
            self._recalculate_series_status(conn, episode["media_id"])
            row = conn.execute(
                """
                SELECT id, media_id, season_number, episode_number, title, synopsis, watched
                FROM episode WHERE id = ?
                """,
                (episode_id,),
            ).fetchone()
        return self._row_to_episode(row)

    async def fetch_all(self) -> List[Media]:
        return await asyncio.to_thread(self._fetch_all_sync)

    async def fetch_one(self, media_id: str) -> Optional[Media]:
        return await asyncio.to_thread(self._fetch_one_sync, media_id)

    async def create(self, fields: Dict[str, Any]) -> Media:
        return await asyncio.to_thread(self._create_sync, fields)

    async def update(self, media_id: str, fields: Dict[str, Any]) -> bool:
        return await asyncio.to_thread(self._update_sync, media_id, fields)

    async def delete(self, media_id: str) -> bool:
        return await asyncio.to_thread(self._delete_sync, media_id)

    async def create_episodes(self, media_id: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._create_episodes_sync, media_id, episodes)

    async def upsert_episodes(self, media_id: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._upsert_episodes_sync, media_id, episodes)

    async def list_episodes(self, media_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_episodes_sync, media_id)

    async def set_episode_watched(self, episode_id: str, watched: bool) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._set_episode_watched_sync, episode_id, watched)

    async def series_progress(self, media_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._series_progress_sync, media_id)
