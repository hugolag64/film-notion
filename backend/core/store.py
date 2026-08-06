"""Persistance locale des médias (SQLite), remplace Notion comme source de vérité."""
import asyncio
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.core.models import Media, Notification, Rental, UserMediaState
from backend.core.media_server import Availability
from backend.core.playback import PlaybackProgress

_COLUMNS = [
    "id", "title", "original_title", "type", "status", "support", "rating", "release_date",
    "director", "categories", "synopsis", "tags", "review", "tmdb_ok", "tmdb_id", "cover_url",
    "watched_in_cinema", "watched_date", "backdrop_url", "cast", "created_at",
]

_LIST_FIELDS = {"categories", "tags", "cast"}
_ACTIVE_RENTAL_STATES = ("requested", "downloading", "available", "keep_requested")


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_availability (
                    media_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    arr_id INTEGER,
                    jellyfin_id TEXT,
                    state TEXT NOT NULL,
                    progress_percent INTEGER,
                    root_folder TEXT,
                    quality_profile_id INTEGER,
                    language_profile_id INTEGER,
                    last_error TEXT,
                    last_synced_at TEXT,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_rentals (
                    id TEXT PRIMARY KEY,
                    media_id TEXT NOT NULL,
                    backstage_user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    available_at TEXT,
                    first_played_at TEXT,
                    expires_at TEXT,
                    keep_requested_at TEXT,
                    storage_policy TEXT NOT NULL DEFAULT 'temporary',
                    rental_scope TEXT NOT NULL DEFAULT 'movie',
                    size_bytes INTEGER,
                    keep_decision TEXT,
                    decided_by TEXT,
                    decided_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            rental_columns = {row[1] for row in conn.execute("PRAGMA table_info(media_rentals)").fetchall()}
            if "storage_policy" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN storage_policy TEXT NOT NULL DEFAULT 'temporary'")
            if "rental_scope" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN rental_scope TEXT NOT NULL DEFAULT 'movie'")
                conn.execute(
                    "UPDATE media_rentals SET rental_scope = 'series' "
                    "WHERE media_id IN (SELECT id FROM media WHERE type = 'Série')"
                )
            if "size_bytes" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN size_bytes INTEGER")
            if "keep_decision" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN keep_decision TEXT")
            if "decided_by" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN decided_by TEXT")
            if "decided_at" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN decided_at TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    backstage_user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    dedupe_key TEXT,
                    read_at TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notifications_user_created "
                "ON notifications(backstage_user_id, created_at DESC)"
            )
            notification_columns = {row[1] for row in conn.execute("PRAGMA table_info(notifications)").fetchall()}
            if "dedupe_key" not in notification_columns:
                conn.execute("ALTER TABLE notifications ADD COLUMN dedupe_key TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedupe "
                "ON notifications(dedupe_key) WHERE dedupe_key IS NOT NULL"
            )
            active_states = ", ".join(f"'{state}'" for state in _ACTIVE_RENTAL_STATES)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_active_media_rentals_user_media "
                f"ON media_rentals(backstage_user_id, media_id) WHERE status IN ({active_states})"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_rentals_user_status "
                "ON media_rentals(backstage_user_id, status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_media_state (
                    backstage_user_id TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    status TEXT,
                    rating TEXT,
                    review TEXT,
                    is_favorite INTEGER NOT NULL DEFAULT 0,
                    added_to_watchlist_at TEXT,
                    first_started_at TEXT,
                    last_interacted_at TEXT NOT NULL,
                    PRIMARY KEY (backstage_user_id, media_id),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_media_state_user_status "
                "ON user_media_state(backstage_user_id, status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playback_progress (
                    backstage_user_id TEXT NOT NULL,
                    jellyfin_id TEXT NOT NULL,
                    media_id TEXT,
                    episode_id TEXT,
                    title TEXT NOT NULL,
                    series_title TEXT,
                    season_number INTEGER,
                    episode_number INTEGER,
                    position_ticks INTEGER NOT NULL DEFAULT 0,
                    runtime_ticks INTEGER NOT NULL DEFAULT 0,
                    percent REAL NOT NULL DEFAULT 0,
                    played INTEGER NOT NULL DEFAULT 0,
                    last_played_at TEXT,
                    synced_at TEXT NOT NULL,
                    PRIMARY KEY (backstage_user_id, jellyfin_id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_playback_user_resume "
                "ON playback_progress(backstage_user_id, played, percent)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_media_availability_arr "
                "ON media_availability(provider, arr_id) WHERE arr_id IS NOT NULL"
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
    def _row_to_rental(row: sqlite3.Row) -> Rental:
        data = dict(row)
        for field in (
            "requested_at", "available_at", "first_played_at", "expires_at",
            "keep_requested_at", "decided_at", "created_at", "updated_at",
        ):
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        return Rental(**data)

    @staticmethod
    def _row_to_notification(row: sqlite3.Row) -> Notification:
        data = dict(row)
        for field in ("read_at", "created_at"):
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        return Notification(**data)

    @staticmethod
    def _row_to_user_media_state(row: sqlite3.Row) -> UserMediaState:
        data = dict(row)
        for field in ("added_to_watchlist_at", "first_started_at", "last_interacted_at"):
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        data["is_favorite"] = bool(data.get("is_favorite", 0))
        return UserMediaState(**data)

    def _get_user_media_state_sync(self, user_id: str, media_id: str) -> Optional[UserMediaState]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM user_media_state WHERE backstage_user_id = ? AND media_id = ?",
                (user_id, media_id),
            ).fetchone()
        return self._row_to_user_media_state(row) if row else None

    def _list_user_media_states_sync(self, user_id: str) -> List[UserMediaState]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM user_media_state WHERE backstage_user_id = ? ORDER BY last_interacted_at DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_user_media_state(row) for row in rows]

    def _upsert_user_media_state_sync(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> UserMediaState:
        allowed = {
            "status", "rating", "review", "is_favorite",
            "added_to_watchlist_at", "first_started_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        now = datetime.now(timezone.utc)
        if "status" in updates and updates["status"] == "À regarder" and "added_to_watchlist_at" not in updates:
            updates["added_to_watchlist_at"] = now
        encoded = {}
        for key, value in updates.items():
            if key in {"added_to_watchlist_at", "first_started_at"} and value is not None:
                encoded[key] = value.isoformat() if isinstance(value, datetime) else value
            elif key == "is_favorite":
                encoded[key] = int(bool(value))
            else:
                encoded[key] = value
        encoded["last_interacted_at"] = now.isoformat()
        columns = ["backstage_user_id", "media_id", *encoded.keys()]
        values = [user_id, media_id, *encoded.values()]
        assignments = ", ".join(f"{column} = excluded.{column}" for column in encoded)
        placeholders = ", ".join("?" for _ in columns)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                f"INSERT INTO user_media_state ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT(backstage_user_id, media_id) DO UPDATE SET {assignments}",
                values,
            )
            row = conn.execute(
                "SELECT * FROM user_media_state WHERE backstage_user_id = ? AND media_id = ?",
                (user_id, media_id),
            ).fetchone()
        return self._row_to_user_media_state(row)

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

    @staticmethod
    def _row_to_availability(row: sqlite3.Row) -> Availability:
        data = dict(row)
        if data.get("last_synced_at"):
            data["last_synced_at"] = datetime.fromisoformat(data["last_synced_at"])
        return Availability(**data)

    def _get_availability_sync(self, media_id: str) -> Optional[Availability]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM media_availability WHERE media_id = ?", (media_id,)
            ).fetchone()
        return self._row_to_availability(row) if row else None

    def _create_rental_sync(self, rental: Rental) -> Rental:
        values = rental.model_dump()
        for field in (
            "requested_at", "available_at", "first_played_at", "expires_at",
            "keep_requested_at", "decided_at", "created_at", "updated_at",
        ):
            if values[field] is not None:
                values[field] = values[field].isoformat()
        columns = list(values)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO media_rentals ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [values[column] for column in columns],
            )
        return self._get_rental_sync(rental.id)

    def _get_rental_sync(self, rental_id: str) -> Optional[Rental]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM media_rentals WHERE id = ?", (rental_id,)).fetchone()
        return self._row_to_rental(row) if row else None

    def _list_user_rentals_sync(self, user_id: str) -> List[Rental]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM media_rentals WHERE backstage_user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_rental(row) for row in rows]

    def _count_active_rentals_sync(self, user_id: str) -> int:
        placeholders = ", ".join("?" for _ in _ACTIVE_RENTAL_STATES)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM media_rentals WHERE backstage_user_id = ? AND status IN ({placeholders})",
                (user_id, *_ACTIVE_RENTAL_STATES),
            ).fetchone()
        return int(row[0])

    def _active_temporary_bytes_sync(self, user_id: Optional[str] = None) -> int:
        placeholders = ", ".join("?" for _ in _ACTIVE_RENTAL_STATES)
        query = (
            "SELECT COALESCE(SUM(size_bytes), 0) FROM media_rentals "
            "WHERE storage_policy = 'temporary' AND status IN (" + placeholders + ")"
        )
        params: tuple[Any, ...] = (*_ACTIVE_RENTAL_STATES,)
        if user_id is not None:
            query += " AND backstage_user_id = ?"
            params += (user_id,)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(query, params).fetchone()
        return int(row[0] or 0)

    def _find_active_rental_sync(self, user_id: str, media_id: str) -> Optional[Rental]:
        placeholders = ", ".join("?" for _ in _ACTIVE_RENTAL_STATES)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM media_rentals WHERE backstage_user_id = ? AND media_id = ? "
                f"AND status IN ({placeholders})",
                (user_id, media_id, *_ACTIVE_RENTAL_STATES),
            ).fetchone()
        return self._row_to_rental(row) if row else None

    def _update_rental_sync(self, rental_id: str, updates: Dict[str, Any]) -> Optional[Rental]:
        allowed = {
            "status", "available_at", "first_played_at", "expires_at", "keep_requested_at",
            "storage_policy", "rental_scope", "size_bytes", "keep_decision", "decided_by", "decided_at", "updated_at",
        }
        values = {key: value for key, value in updates.items() if key in allowed}
        values["updated_at"] = values.get("updated_at") or datetime.now(timezone.utc)
        for key, value in values.items():
            if isinstance(value, datetime):
                values[key] = value.isoformat()
        if values:
            assignments = ", ".join(f"{key} = ?" for key in values)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    f"UPDATE media_rentals SET {assignments} WHERE id = ?",
                    (*values.values(), rental_id),
                )
        return self._get_rental_sync(rental_id)

    def _list_keep_requested_rentals_sync(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT media_rentals.*, media.title AS media_title "
                "FROM media_rentals JOIN media ON media.id = media_rentals.media_id "
                "WHERE media_rentals.status = 'keep_requested' ORDER BY media_rentals.updated_at DESC"
            ).fetchall()
        items = []
        for row in rows:
            items.append({
                "media_title": row["media_title"],
                "rental": self._row_to_rental(row).model_dump(mode="json"),
            })
        return items

    def _list_admin_rentals_sync(self) -> List[Dict[str, Any]]:
        states = (*_ACTIVE_RENTAL_STATES, "kept")
        placeholders = ", ".join("?" for _ in states)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT media_rentals.*, media.title AS media_title "
                "FROM media_rentals JOIN media ON media.id = media_rentals.media_id "
                f"WHERE media_rentals.status IN ({placeholders}) "
                "ORDER BY media_rentals.expires_at IS NULL, media_rentals.expires_at",
                states,
            ).fetchall()
        return [
            {"media_title": row["media_title"], "rental": self._row_to_rental(row)}
            for row in rows
        ]

    def _decide_rental_sync(self, rental_id: str, decision: str, admin_id: str, decided_at: datetime) -> Optional[Rental]:
        if decision not in {"accepted", "refused"}:
            raise ValueError("invalid rental decision")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT status FROM media_rentals WHERE id = ?", (rental_id,)).fetchone()
            if not row:
                return None
            if row[0] != "keep_requested":
                raise ValueError("rental is not awaiting a conservation decision")
            if decision == "accepted":
                conn.execute(
                    "UPDATE media_rentals SET status = 'kept', storage_policy = 'permanent', "
                    "keep_decision = 'accepted', expires_at = NULL, keep_requested_at = NULL, "
                    "decided_by = ?, decided_at = ?, updated_at = ? WHERE id = ?",
                    (admin_id, decided_at.isoformat(), decided_at.isoformat(), rental_id),
                )
            else:
                conn.execute(
                    "UPDATE media_rentals SET status = 'available', storage_policy = 'temporary', "
                    "keep_decision = 'refused', keep_requested_at = NULL, decided_by = ?, "
                    "decided_at = ?, updated_at = ? WHERE id = ?",
                    (admin_id, decided_at.isoformat(), decided_at.isoformat(), rental_id),
                )
        return self._get_rental_sync(rental_id)

    def _extend_rental_sync(self, rental_id: str, now: datetime) -> Optional[Rental]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT status, expires_at FROM media_rentals WHERE id = ?", (rental_id,)).fetchone()
            if not row:
                return None
            if row["status"] not in {"available", "keep_requested"}:
                raise ValueError("rental cannot be extended")
            current_expiry = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else now
            expiry = max(current_expiry, now) + timedelta(days=7)
            conn.execute(
                "UPDATE media_rentals SET expires_at = ?, updated_at = ? WHERE id = ?",
                (expiry.isoformat(), now.isoformat(), rental_id),
            )
        return self._get_rental_sync(rental_id)

    def _create_notification_sync(self, notification: Notification) -> Notification:
        values = notification.model_dump()
        for field in ("read_at", "created_at"):
            if values[field] is not None:
                values[field] = values[field].isoformat()
        columns = list(values)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO notifications ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [values[column] for column in columns],
            )
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM notifications WHERE id = ? OR (? IS NOT NULL AND dedupe_key = ?)",
                (notification.id, notification.dedupe_key, notification.dedupe_key),
            ).fetchone()
        return self._row_to_notification(row)

    def _list_notifications_sync(self, user_id: str) -> List[Notification]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM notifications WHERE backstage_user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_notification(row) for row in rows]

    def _mark_notification_read_sync(self, notification_id: str, user_id: str, read_at: datetime) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE notifications SET read_at = ? WHERE id = ? AND backstage_user_id = ?",
                (read_at.isoformat(), notification_id, user_id),
            )
        return cursor.rowcount > 0

    def _mark_rentals_available_sync(
        self, media_id: str, available_at: datetime, expires_at: datetime,
        size_bytes: Optional[int] = None,
    ) -> int:
        active_states = ("requested", "downloading", "available")
        placeholders = ", ".join("?" for _ in active_states)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE media_rentals SET status = 'available', available_at = COALESCE(available_at, ?), "
                f"expires_at = COALESCE(expires_at, ?), size_bytes = COALESCE(size_bytes, ?), updated_at = ? "
                f"WHERE media_id = ? AND status IN ({placeholders})",
                (available_at.isoformat(), expires_at.isoformat(), size_bytes, available_at.isoformat(), media_id, *active_states),
            )
        return cursor.rowcount

    def _mark_rental_first_played_sync(
        self, user_id: str, media_id: str, first_played_at: datetime, expires_at: datetime,
    ) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE media_rentals SET first_played_at = ?, expires_at = ?, updated_at = ? "
                "WHERE backstage_user_id = ? AND media_id = ? AND status = 'available' AND first_played_at IS NULL",
                (first_played_at.isoformat(), expires_at.isoformat(), first_played_at.isoformat(), user_id, media_id),
            )
        return cursor.rowcount > 0

    def _cleanup_preview_sync(self, now: datetime) -> List[Dict[str, Any]]:
        active_states = ("requested", "downloading", "available", "keep_requested")
        placeholders = ", ".join("?" for _ in active_states)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT media_rentals.*, media.title AS media_title FROM media_rentals "
                "JOIN media ON media.id = media_rentals.media_id "
                "WHERE media_rentals.status IN ('available', 'keep_requested', 'kept') "
                "AND (media_rentals.expires_at IS NULL OR media_rentals.expires_at <= ?) "
                "ORDER BY media_rentals.expires_at IS NULL, media_rentals.expires_at",
                (now.isoformat(),),
            ).fetchall()
            preview = []
            for row in rows:
                reason = None
                if row["storage_policy"] == "permanent" or row["status"] == "kept":
                    reason = "permanent"
                elif row["status"] == "keep_requested":
                    reason = "conservation_pending"
                else:
                    other_active = conn.execute(
                        f"SELECT 1 FROM media_rentals WHERE media_id = ? AND id != ? AND status IN ({placeholders}) LIMIT 1",
                        (row["media_id"], row["id"], *active_states),
                    ).fetchone()
                    if other_active:
                        reason = "other_active_rental"
                    else:
                        playing = conn.execute(
                            "SELECT 1 FROM playback_progress WHERE media_id = ? AND played = 0 AND percent > 0 LIMIT 1",
                            (row["media_id"],),
                        ).fetchone()
                        if playing:
                            reason = "playback_in_progress"
                preview.append({
                    "rental_id": row["id"], "media_id": row["media_id"],
                    "media_title": row["media_title"], "status": row["status"],
                    "storage_policy": row["storage_policy"], "expires_at": row["expires_at"],
                    "action": "protected" if reason else "would_delete", "reason": reason,
                })
        return preview

    def _upsert_availability_sync(self, availability: Availability) -> Availability:
        values = availability.model_dump()
        if values["last_synced_at"] is not None:
            values["last_synced_at"] = values["last_synced_at"].isoformat()
        columns = list(values)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO media_availability ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
                "ON CONFLICT(media_id) DO UPDATE SET " + ", ".join(
                    f"{column} = excluded.{column}" for column in columns if column != "media_id"
                ),
                [values[column] for column in columns],
            )
        return self._get_availability_sync(availability.media_id)

    def _list_availabilities_sync(self) -> List[Availability]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM media_availability ORDER BY last_synced_at DESC").fetchall()
        return [self._row_to_availability(row) for row in rows]

    @staticmethod
    def _row_to_playback(row: sqlite3.Row) -> PlaybackProgress:
        data = dict(row)
        for field in ("last_played_at", "synced_at"):
            if data.get(field):
                data[field] = datetime.fromisoformat(data[field])
        data["played"] = bool(data["played"])
        return PlaybackProgress(**data)

    @staticmethod
    def _playback_values(progress: PlaybackProgress) -> Dict[str, Any]:
        values = progress.model_dump()
        for field in ("last_played_at", "synced_at"):
            if values[field] is not None:
                values[field] = values[field].isoformat()
        values["played"] = int(values["played"])
        return values

    def _upsert_playback_sync(self, progress: PlaybackProgress) -> PlaybackProgress:
        values = self._playback_values(progress)
        columns = list(values)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO playback_progress ({', '.join(columns)}) VALUES "
                f"({', '.join('?' for _ in columns)}) ON CONFLICT(backstage_user_id, jellyfin_id) DO UPDATE SET "
                + ", ".join(f"{column} = excluded.{column}" for column in columns if column not in {"backstage_user_id", "jellyfin_id"}),
                [values[column] for column in columns],
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM playback_progress WHERE backstage_user_id = ? AND jellyfin_id = ?",
                (progress.backstage_user_id, progress.jellyfin_id),
            ).fetchone()
        return self._row_to_playback(row)

    def _resolve_playback_item_sync(self, item: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        with sqlite3.connect(self.db_path) as conn:
            jellyfin_ids = [
                value for value in (item.get("jellyfin_id"), item.get("series_jellyfin_id"))
                if value
            ]
            media_id = None
            if jellyfin_ids:
                placeholders = ", ".join("?" for _ in jellyfin_ids)
                row = conn.execute(
                    f"SELECT media_id FROM media_availability WHERE jellyfin_id IN ({placeholders}) LIMIT 1",
                    jellyfin_ids,
                ).fetchone()
                media_id = row[0] if row else None
            if media_id is None and item.get("tmdb_id") is not None:
                media_type = "Série" if item.get("item_type") in {"Series", "Episode"} or item.get("series_title") else "Film"
                row = conn.execute(
                    "SELECT id FROM media WHERE tmdb_id = ? AND type = ? LIMIT 1",
                    (item["tmdb_id"], media_type),
                ).fetchone()
                media_id = row[0] if row else None
            episode_id = None
            if media_id and item.get("season_number") is not None and item.get("episode_number") is not None:
                row = conn.execute(
                    "SELECT id FROM episode WHERE media_id = ? AND season_number = ? AND episode_number = ?",
                    (media_id, item["season_number"], item["episode_number"]),
                ).fetchone()
                episode_id = row[0] if row else None
        return media_id, episode_id

    def _list_playback_sync(self, user_id: str, completed: bool) -> List[PlaybackProgress]:
        clause = "(played = 1 OR percent >= 95)" if completed else "played = 0 AND percent < 95"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM playback_progress WHERE backstage_user_id = ? AND {clause} "
                "AND media_id IS NOT NULL ORDER BY COALESCE(last_played_at, synced_at) DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_playback(row) for row in rows]

    def _list_next_episodes_sync(self, user_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            series_rows = conn.execute(
                "SELECT DISTINCT media_id FROM playback_progress "
                "WHERE backstage_user_id = ? AND media_id IS NOT NULL AND series_title IS NOT NULL",
                (user_id,),
            ).fetchall()
            output = []
            for series_row in series_rows:
                media_id = series_row["media_id"]
                episodes = conn.execute(
                    "SELECT id, season_number, episode_number, title FROM episode "
                    "WHERE media_id = ? ORDER BY season_number, episode_number",
                    (media_id,),
                ).fetchall()
                progress_rows = conn.execute(
                    "SELECT * FROM playback_progress WHERE backstage_user_id = ? AND media_id = ?",
                    (user_id, media_id),
                ).fetchall()
                progress = {
                    (row["season_number"], row["episode_number"]): row
                    for row in progress_rows
                }
                for episode in episodes:
                    row = progress.get((episode["season_number"], episode["episode_number"]))
                    complete = row and (row["played"] or row["percent"] >= 95)
                    if complete:
                        continue
                    output.append({
                        "media_id": media_id,
                        "episode_id": episode["id"],
                        "title": episode["title"],
                        "season_number": episode["season_number"],
                        "episode_number": episode["episode_number"],
                        "percent": round(float(row["percent"]), 2) if row else 0,
                        "jellyfin_id": row["jellyfin_id"] if row else None,
                    })
                    break
        return output

    def _last_playback_sync_sync(self, user_id: str) -> Optional[datetime]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(synced_at) FROM playback_progress WHERE backstage_user_id = ?",
                (user_id,),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None

    async def fetch_all(self) -> List[Media]:
        return await asyncio.to_thread(self._fetch_all_sync)

    async def fetch_one(self, media_id: str) -> Optional[Media]:
        return await asyncio.to_thread(self._fetch_one_sync, media_id)

    async def get_user_media_state(self, user_id: str, media_id: str) -> Optional[UserMediaState]:
        return await asyncio.to_thread(self._get_user_media_state_sync, user_id, media_id)

    async def list_user_media_states(self, user_id: str) -> List[UserMediaState]:
        return await asyncio.to_thread(self._list_user_media_states_sync, user_id)

    async def upsert_user_media_state(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> UserMediaState:
        return await asyncio.to_thread(self._upsert_user_media_state_sync, user_id, media_id, fields)

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

    async def get_availability(self, media_id: str) -> Optional[Availability]:
        return await asyncio.to_thread(self._get_availability_sync, media_id)

    async def create_rental(self, rental: Rental) -> Rental:
        return await asyncio.to_thread(self._create_rental_sync, rental)

    async def get_rental(self, rental_id: str) -> Optional[Rental]:
        return await asyncio.to_thread(self._get_rental_sync, rental_id)

    async def list_user_rentals(self, user_id: str) -> List[Rental]:
        return await asyncio.to_thread(self._list_user_rentals_sync, user_id)

    async def count_active_rentals(self, user_id: str) -> int:
        return await asyncio.to_thread(self._count_active_rentals_sync, user_id)

    async def active_temporary_bytes(self, user_id: Optional[str] = None) -> int:
        return await asyncio.to_thread(self._active_temporary_bytes_sync, user_id)

    async def find_active_rental(self, user_id: str, media_id: str) -> Optional[Rental]:
        return await asyncio.to_thread(self._find_active_rental_sync, user_id, media_id)

    async def update_rental(self, rental_id: str, updates: Dict[str, Any]) -> Optional[Rental]:
        return await asyncio.to_thread(self._update_rental_sync, rental_id, updates)

    async def list_keep_requested_rentals(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_keep_requested_rentals_sync)

    async def list_admin_rentals(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_admin_rentals_sync)

    async def decide_rental(
        self, rental_id: str, decision: str, admin_id: str, decided_at: datetime,
    ) -> Optional[Rental]:
        return await asyncio.to_thread(self._decide_rental_sync, rental_id, decision, admin_id, decided_at)

    async def extend_rental(self, rental_id: str, now: datetime) -> Optional[Rental]:
        return await asyncio.to_thread(self._extend_rental_sync, rental_id, now)

    async def create_notification(self, notification: Notification) -> Notification:
        return await asyncio.to_thread(self._create_notification_sync, notification)

    async def list_notifications(self, user_id: str) -> List[Notification]:
        return await asyncio.to_thread(self._list_notifications_sync, user_id)

    async def mark_notification_read(self, notification_id: str, user_id: str, read_at: datetime) -> bool:
        return await asyncio.to_thread(self._mark_notification_read_sync, notification_id, user_id, read_at)

    async def mark_rentals_available(
        self, media_id: str, available_at: datetime, expires_at: datetime,
        size_bytes: Optional[int] = None,
    ) -> int:
        return await asyncio.to_thread(self._mark_rentals_available_sync, media_id, available_at, expires_at, size_bytes)

    async def mark_rental_first_played(
        self, user_id: str, media_id: str, first_played_at: datetime, expires_at: datetime,
    ) -> bool:
        return await asyncio.to_thread(self._mark_rental_first_played_sync, user_id, media_id, first_played_at, expires_at)

    async def cleanup_preview(self, now: datetime) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._cleanup_preview_sync, now)

    async def upsert_availability(self, availability: Availability) -> Availability:
        return await asyncio.to_thread(self._upsert_availability_sync, availability)

    def _clear_arr_id_conflict_sync(self, provider: str, arr_id: int, media_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE media_availability SET arr_id = NULL, last_error = ? "
                "WHERE provider = ? AND arr_id = ? AND media_id != ?",
                ("Lien serveur réinitialisé après réattribution", provider, arr_id, media_id),
            )

    async def clear_arr_id_conflict(self, provider: str, arr_id: int, media_id: str) -> None:
        await asyncio.to_thread(self._clear_arr_id_conflict_sync, provider, arr_id, media_id)

    async def list_availabilities(self) -> List[Availability]:
        return await asyncio.to_thread(self._list_availabilities_sync)

    async def upsert_playback(self, progress: PlaybackProgress) -> PlaybackProgress:
        return await asyncio.to_thread(self._upsert_playback_sync, progress)

    async def resolve_playback_item(self, item: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        return await asyncio.to_thread(self._resolve_playback_item_sync, item)

    async def list_resume_progress(self, user_id: str) -> List[PlaybackProgress]:
        return await asyncio.to_thread(self._list_playback_sync, user_id, False)

    async def list_recently_completed(self, user_id: str) -> List[PlaybackProgress]:
        return await asyncio.to_thread(self._list_playback_sync, user_id, True)

    async def list_next_episodes(self, user_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_next_episodes_sync, user_id)

    async def last_playback_sync(self, user_id: str) -> Optional[datetime]:
        return await asyncio.to_thread(self._last_playback_sync_sync, user_id)
