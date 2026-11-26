"""Persistance locale des médias (SQLite), remplace Notion comme source de vérité."""
import asyncio
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.core.cinema_store import create_cinema_tables
from backend.core.models import (
    DiaryEntry, FilmList, FilmListItem,
    Media, Notification, RecommendationEvent, RecommendationSession,
    Rental, UserEpisodeState, UserMediaState,
)
from backend.core.media_server import Availability
from backend.core.playback import PlaybackProgress

_COLUMNS = [
    "id", "title", "original_title", "type", "status", "support", "rating", "release_date",
    "director", "categories", "synopsis", "tags", "review", "tmdb_ok", "tmdb_id", "cover_url",
    "watched_in_cinema", "watched_date", "backdrop_url", "cast", "created_at",
]

_LIST_FIELDS = {"categories", "tags", "cast"}
_ACTIVE_RENTAL_STATES = ("requested", "downloading", "available", "keep_requested")
# A requested rental is "waiting for a source" while Radarr has nothing to download yet.
_WAITING_DOWNLOAD_STATES = ("requested", "error")


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
            episode_columns = {row[1] for row in conn.execute("PRAGMA table_info(episode)").fetchall()}
            for column, sql_type in (("air_date", "TEXT"), ("runtime", "INTEGER"), ("still_url", "TEXT")):
                if column not in episode_columns:
                    conn.execute(f"ALTER TABLE episode ADD COLUMN {column} {sql_type}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS series_season (
                    media_id TEXT NOT NULL,
                    season_number INTEGER NOT NULL,
                    name TEXT,
                    overview TEXT,
                    poster_url TEXT,
                    air_date TEXT,
                    PRIMARY KEY (media_id, season_number),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS series_info (
                    media_id TEXT PRIMARY KEY,
                    tmdb_status TEXT,
                    first_air_date TEXT,
                    last_air_date TEXT,
                    number_of_seasons INTEGER,
                    vote_average REAL,
                    next_air_date TEXT,
                    next_season_number INTEGER,
                    next_episode_number INTEGER,
                    next_episode_name TEXT,
                    updated_at TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS user_episode_state (
                    backstage_user_id TEXT NOT NULL,
                    episode_id TEXT NOT NULL,
                    watched INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (backstage_user_id, episode_id),
                    FOREIGN KEY (episode_id) REFERENCES episode(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_episode_state_user_watched "
                "ON user_episode_state(backstage_user_id, watched)"
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
            if "season_number" not in rental_columns:
                conn.execute("ALTER TABLE media_rentals ADD COLUMN season_number INTEGER")
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    author_avatar_url TEXT,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            notification_columns = {row[1] for row in conn.execute("PRAGMA table_info(notifications)").fetchall()}
            if "dedupe_key" not in notification_columns:
                conn.execute("ALTER TABLE notifications ADD COLUMN dedupe_key TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedupe "
                "ON notifications(dedupe_key) WHERE dedupe_key IS NOT NULL"
            )
            active_states = ", ".join(f"'{state}'" for state in _ACTIVE_RENTAL_STATES)
            # One active rental per user and media — per season for season rentals.
            conn.execute("DROP INDEX IF EXISTS idx_active_media_rentals_user_media")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_active_media_rentals_user_media_season "
                "ON media_rentals(backstage_user_id, media_id, COALESCE(season_number, -1)) "
                f"WHERE status IN ({active_states})"
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
                    is_watchlist INTEGER NOT NULL DEFAULT 0,
                    added_to_watchlist_at TEXT,
                    first_started_at TEXT,
                    last_interacted_at TEXT NOT NULL,
                    PRIMARY KEY (backstage_user_id, media_id),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            user_media_state_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(user_media_state)").fetchall()
            }
            if "is_watchlist" not in user_media_state_columns:
                conn.execute(
                    "ALTER TABLE user_media_state ADD COLUMN is_watchlist INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_media_state_user_status "
                "ON user_media_state(backstage_user_id, status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_events (
                    id TEXT PRIMARY KEY,
                    backstage_user_id TEXT NOT NULL,
                    session_id TEXT,
                    media_id TEXT,
                    event_type TEXT NOT NULL,
                    value TEXT,
                    numeric_value REAL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recommendation_events_user_created "
                "ON recommendation_events(backstage_user_id, created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recommendation_sessions (
                    id TEXT PRIMARY KEY,
                    backstage_user_id TEXT NOT NULL,
                    question_count INTEGER NOT NULL DEFAULT 0,
                    session_preferences TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recommendation_sessions_user_status "
                "ON recommendation_sessions(backstage_user_id, status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_recommendation_sessions_user_created "
                "ON recommendation_sessions(backstage_user_id, created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_recommendation_preferences (
                    backstage_user_id TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    fields TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (backstage_user_id, media_id),
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_recommendation_preferences_user_updated "
                "ON media_recommendation_preferences(backstage_user_id, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_recommendation_preferences_media_updated "
                "ON media_recommendation_preferences(media_id, updated_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ai_usage (
                    id TEXT PRIMARY KEY,
                    backstage_user_id TEXT NOT NULL,
                    session_id TEXT,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_estimate_usd REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'success',
                    error TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            ai_usage_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_usage)").fetchall()}
            if "status" not in ai_usage_columns:
                conn.execute("ALTER TABLE ai_usage ADD COLUMN status TEXT NOT NULL DEFAULT 'success'")
            if "error" not in ai_usage_columns:
                conn.execute("ALTER TABLE ai_usage ADD COLUMN error TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_usage_user_created "
                "ON ai_usage(backstage_user_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_usage_session_created "
                "ON ai_usage(session_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at "
                "ON ai_usage(created_at DESC)"
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_storage_protection (
                    media_id TEXT PRIMARY KEY,
                    protected INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS storage_cleanup_log (
                    id TEXT PRIMARY KEY,
                    admin_user_id TEXT NOT NULL,
                    media_id TEXT NOT NULL,
                    media_title TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_storage_cleanup_log_deleted_at "
                "ON storage_cleanup_log(deleted_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tmdb_movie_cache (
                    tmdb_id INTEGER PRIMARY KEY,
                    title TEXT NOT NULL,
                    year INTEGER,
                    release_date TEXT,
                    poster_url TEXT,
                    genres TEXT NOT NULL DEFAULT '[]',
                    fetched_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diary_entries (
                    id TEXT PRIMARY KEY,
                    backstage_user_id TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    watched_on TEXT,
                    rating REAL,
                    review TEXT,
                    in_cinema INTEGER NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_diary_entries_user_tmdb "
                "ON diary_entries(backstage_user_id, tmdb_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS film_lists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS film_list_items (
                    list_id TEXT NOT NULL,
                    tmdb_id INTEGER NOT NULL,
                    added_by TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (list_id, tmdb_id),
                    FOREIGN KEY (list_id) REFERENCES film_lists(id) ON DELETE CASCADE
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
            chat_columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
            if "payload" not in chat_columns:
                conn.execute("ALTER TABLE chat_messages ADD COLUMN payload TEXT")
            tmdb_cache_columns = {row[1] for row in conn.execute("PRAGMA table_info(tmdb_movie_cache)").fetchall()}
            if "fr_release_date" not in tmdb_cache_columns:
                conn.execute("ALTER TABLE tmdb_movie_cache ADD COLUMN fr_release_date TEXT")
            create_cinema_tables(conn)


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
        data["is_watchlist"] = bool(data.get("is_watchlist", 0))
        return UserMediaState(**data)

    @staticmethod
    def _row_to_recommendation_event(row: sqlite3.Row) -> RecommendationEvent:
        data = dict(row)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return RecommendationEvent(**data)

    @staticmethod
    def _row_to_recommendation_session(row: sqlite3.Row) -> RecommendationSession:
        data = dict(row)
        data["session_preferences"] = json.loads(data.get("session_preferences") or "{}")
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("completed_at"):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
        return RecommendationSession(**data)

    @staticmethod
    def _row_to_media_recommendation_preference(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["fields"] = json.loads(data.get("fields") or "{}")
        return data

    @staticmethod
    def _row_to_ai_usage(row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row)

    def _record_recommendation_event_sync(self, event: RecommendationEvent) -> RecommendationEvent:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO recommendation_events "
                "(id, backstage_user_id, session_id, media_id, event_type, value, numeric_value, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id, event.backstage_user_id, event.session_id, event.media_id,
                    event.event_type, event.value, event.numeric_value, event.created_at.isoformat(),
                ),
            )
        return event

    def _list_recommendation_events_sync(self, user_id: str) -> List[RecommendationEvent]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM recommendation_events WHERE backstage_user_id = ? "
                "ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_recommendation_event(row) for row in rows]

    def _create_recommendation_session_sync(self, session: RecommendationSession) -> RecommendationSession:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO recommendation_sessions "
                "(id, backstage_user_id, question_count, session_preferences, status, created_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session.id, session.backstage_user_id, session.question_count,
                    json.dumps(session.session_preferences), session.status,
                    session.created_at.isoformat(),
                    session.completed_at.isoformat() if session.completed_at else None,
                ),
            )
        return session

    def _create_recommendation_session_if_available_sync(
        self, session: RecommendationSession, limit: int, day_start: Any,
    ) -> Optional[RecommendationSession]:
        day_start_iso = self._coerce_iso_datetime(day_start)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute(
                "SELECT COUNT(*) FROM recommendation_sessions "
                "WHERE backstage_user_id = ? AND created_at >= ? AND status != 'cancelled'",
                (session.backstage_user_id, day_start_iso),
            ).fetchone()[0]
            if count >= limit:
                return None
            conn.execute(
                "INSERT INTO recommendation_sessions "
                "(id, backstage_user_id, question_count, session_preferences, status, created_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session.id, session.backstage_user_id, session.question_count,
                    json.dumps(session.session_preferences), session.status,
                    session.created_at.isoformat(), session.completed_at.isoformat() if session.completed_at else None,
                ),
            )
        return session

    def _get_recommendation_session_sync(self, session_id: str) -> Optional[RecommendationSession]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM recommendation_sessions WHERE id = ?", (session_id,),
            ).fetchone()
        return self._row_to_recommendation_session(row) if row else None

    def _update_recommendation_session_sync(
        self, session_id: str, fields: Dict[str, Any],
    ) -> Optional[RecommendationSession]:
        allowed = {"question_count", "session_preferences", "status", "completed_at"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if "session_preferences" in updates:
            updates["session_preferences"] = json.dumps(updates["session_preferences"])
        if updates.get("completed_at"):
            completed_at = updates["completed_at"]
            updates["completed_at"] = completed_at.isoformat() if isinstance(completed_at, datetime) else completed_at
        if not updates:
            return self._get_recommendation_session_sync(session_id)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE recommendation_sessions SET {assignments} WHERE id = ?",
                [*updates.values(), session_id],
            )
        return self._get_recommendation_session_sync(session_id)

    def _advance_recommendation_session_sync(
        self, session_id: str, expected_question_count: int, preferences: Dict[str, Any],
    ) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE recommendation_sessions SET question_count = question_count + 1, session_preferences = ? "
                "WHERE id = ? AND status = 'active' AND question_count = ?",
                (json.dumps(preferences), session_id, expected_question_count),
            )
        return cursor.rowcount == 1
    @staticmethod
    def _coerce_iso_datetime(value: Any) -> str:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return str(value)

    def _count_recommendation_sessions_sync(self, user_id: str, day_start: Any) -> int:
        day_start_iso = self._coerce_iso_datetime(day_start)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM recommendation_sessions "
                "WHERE backstage_user_id = ? AND created_at >= ? AND status != 'cancelled'",
                (user_id, day_start_iso),
            ).fetchone()
        return int(row[0] or 0)

    def _get_recommendation_usage_sync(self, session_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ai_usage WHERE session_id = ? ORDER BY created_at ASC, id ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_ai_usage(row) for row in rows]

    def _record_recommendation_usage_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        usage_id = payload.get("id") or str(uuid.uuid4())
        created_at = self._coerce_iso_datetime(payload.get("created_at") or datetime.now(timezone.utc))
        values = {
            "id": usage_id,
            "backstage_user_id": payload["backstage_user_id"],
            "session_id": payload.get("session_id"),
            "model": payload["model"],
            "input_tokens": payload.get("input_tokens", 0),
            "output_tokens": payload.get("output_tokens", 0),
            "cost_estimate_usd": payload.get("cost_estimate_usd", 0),
            "status": payload.get("status", "success"),
            "error": payload.get("error"),
            "created_at": created_at,
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO ai_usage
                (id, backstage_user_id, session_id, model, input_tokens, output_tokens, cost_estimate_usd, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(values[column] for column in (
                    "id", "backstage_user_id", "session_id", "model",
                    "input_tokens", "output_tokens", "cost_estimate_usd", "status", "error", "created_at",
                )),
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ai_usage WHERE id = ?", (usage_id,)).fetchone()
        return self._row_to_ai_usage(row)

    def _upsert_media_recommendation_preference_sync(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        fields_json = json.dumps(fields or {})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO media_recommendation_preferences
                (backstage_user_id, media_id, fields, created_at, updated_at)
                VALUES (?, ?, ?, COALESCE((SELECT created_at FROM media_recommendation_preferences
                    WHERE backstage_user_id = ? AND media_id = ?), ?), ?)
                ON CONFLICT(backstage_user_id, media_id) DO UPDATE SET
                    fields = excluded.fields,
                    updated_at = excluded.updated_at
                """,
                (user_id, media_id, fields_json, user_id, media_id, now, now),
            )
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM media_recommendation_preferences WHERE backstage_user_id = ? AND media_id = ?",
                (user_id, media_id),
            ).fetchone()
        return self._row_to_media_recommendation_preference(row)

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

    def _storage_context_sync(self, watched_since: datetime) -> Dict[str, Any]:
        """Return cross-user signals used to protect media from deletion."""
        with sqlite3.connect(self.db_path) as conn:
            favorite_rows = conn.execute(
                "SELECT DISTINCT media_id FROM user_media_state WHERE is_favorite = 1"
            ).fetchall()
            protection_rows = conn.execute(
                "SELECT media_id, protected FROM media_storage_protection"
            ).fetchall()
            rental_rows = conn.execute(
                "SELECT DISTINCT media_id FROM media_rentals "
                "WHERE status IN ('requested', 'downloading', 'available', 'keep_requested', 'kept') "
                "OR storage_policy = 'permanent'"
            ).fetchall()
            expired_rows = conn.execute(
                "SELECT DISTINCT media_id FROM media_rentals WHERE status = 'expired'"
            ).fetchall()
            playback_rows = conn.execute(
                "SELECT media_id, MAX(last_played_at) FROM playback_progress "
                "WHERE media_id IS NOT NULL AND last_played_at IS NOT NULL "
                "GROUP BY media_id"
            ).fetchall()

        last_playback = {}
        recent_playback = {}
        for media_id, last_played_at in playback_rows:
            played_at = datetime.fromisoformat(last_played_at)
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)
            last_playback[media_id] = played_at
            if played_at >= watched_since:
                recent_playback[media_id] = played_at
        return {
            "favorite_media_ids": {row[0] for row in favorite_rows},
            "protected_media_ids": {row[0] for row in protection_rows if row[1]},
            "rental_media_ids": {row[0] for row in rental_rows},
            "expired_rental_media_ids": {row[0] for row in expired_rows} - {row[0] for row in rental_rows},
            "last_playback": last_playback,
            "recent_playback": recent_playback,
        }

    def _set_storage_protection_sync(self, media_id: str, protected: bool) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            media = conn.execute("SELECT 1 FROM media WHERE id = ?", (media_id,)).fetchone()
            if not media:
                return False
            conn.execute(
                "INSERT INTO media_storage_protection (media_id, protected, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(media_id) DO UPDATE SET protected = excluded.protected, updated_at = excluded.updated_at",
                (media_id, int(protected), now),
            )
        return True

    def _record_storage_cleanup_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        deleted_at = payload.get("deleted_at") or datetime.now(timezone.utc)
        if isinstance(deleted_at, datetime):
            deleted_at = deleted_at.isoformat()
        values = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "admin_user_id": payload["admin_user_id"],
            "media_id": payload["media_id"],
            "media_title": payload["media_title"],
            "size_bytes": int(payload.get("size_bytes") or 0),
            "deleted_at": deleted_at,
            "status": payload.get("status", "deleted"),
            "error": payload.get("error"),
        }
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO storage_cleanup_log "
                "(id, admin_user_id, media_id, media_title, size_bytes, deleted_at, status, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(values[column] for column in (
                    "id", "admin_user_id", "media_id", "media_title", "size_bytes",
                    "deleted_at", "status", "error",
                )),
            )
        return values

    def _list_storage_cleanup_log_sync(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT id, admin_user_id, media_id, media_title, size_bytes, deleted_at, status, error "
                "FROM storage_cleanup_log ORDER BY deleted_at DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def _upsert_user_media_state_sync(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> UserMediaState:
        allowed = {
            "status", "rating", "review", "is_favorite", "is_watchlist",
            "added_to_watchlist_at", "first_started_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        now = datetime.now(timezone.utc)
        if updates.get("is_watchlist") is True and "added_to_watchlist_at" not in updates:
            updates["added_to_watchlist_at"] = now
        encoded = {}
        for key, value in updates.items():
            if key in {"added_to_watchlist_at", "first_started_at"} and value is not None:
                encoded[key] = value.isoformat() if isinstance(value, datetime) else value
            elif key == "is_favorite":
                encoded[key] = int(bool(value))
            elif key == "is_watchlist":
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
        # Foreign keys are not enforced on these connections, so the ON DELETE
        # CASCADE clauses never fire: clean the dependent rows explicitly.
        # Rental history, recommendation events and the cleanup log are kept.
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM user_episode_state WHERE episode_id IN "
                "(SELECT id FROM episode WHERE media_id = ?)",
                (media_id,),
            )
            for table in (
                "episode", "media_availability", "user_media_state",
                "media_recommendation_preferences", "media_storage_protection",
                "series_season", "series_info",
            ):
                conn.execute(f"DELETE FROM {table} WHERE media_id = ?", (media_id,))
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
                       episode.episode_number, episode.title, episode.synopsis, episode.watched,
                       episode.air_date, episode.runtime, episode.still_url
                FROM episode
                JOIN media ON media.id = episode.media_id
                WHERE episode.media_id = ? AND substr(media.type, 1, 1) = 'S' AND substr(media.type, -3) = 'rie'
                ORDER BY episode.season_number, episode.episode_number
                """,
                (media_id,),
            ).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def _list_episodes_for_user_sync(self, media_id: str, user_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT episode.id, episode.media_id, episode.season_number,
                       episode.episode_number, episode.title, episode.synopsis,
                       episode.air_date, episode.runtime, episode.still_url,
                       COALESCE(user_episode_state.watched, 0) AS watched
                FROM episode
                JOIN media ON media.id = episode.media_id
                LEFT JOIN user_episode_state
                  ON user_episode_state.episode_id = episode.id
                 AND user_episode_state.backstage_user_id = ?
                WHERE episode.media_id = ? AND substr(media.type, 1, 1) = 'S' AND substr(media.type, -3) = 'rie'
                ORDER BY episode.season_number, episode.episode_number
                """,
                (user_id, media_id),
            ).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def _series_progress_sync(self, media_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            media = conn.execute(
                "SELECT id FROM media WHERE id = ? AND substr(type, 1, 1) = 'S' AND substr(type, -3) = 'rie'", (media_id,)
            ).fetchone()
            if not media:
                return None
            rows = conn.execute(
                "SELECT season_number, watched FROM episode WHERE media_id = ?",
                (media_id,),
            ).fetchall()
        return self._progress_from_rows(media_id, rows)

    def _series_progress_for_user_sync(self, media_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            media = conn.execute(
                "SELECT id FROM media WHERE id = ? AND substr(type, 1, 1) = 'S' AND substr(type, -3) = 'rie'", (media_id,)
            ).fetchone()
            if not media:
                return None
            rows = conn.execute(
                """
                SELECT episode.season_number,
                       COALESCE(user_episode_state.watched, 0) AS watched
                FROM episode
                LEFT JOIN user_episode_state
                  ON user_episode_state.episode_id = episode.id
                 AND user_episode_state.backstage_user_id = ?
                WHERE episode.media_id = ?
                """,
                (user_id, media_id),
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
                "SELECT id FROM media WHERE id = ? AND substr(type, 1, 1) = 'S' AND substr(type, -3) = 'rie'", (media_id,)
            ).fetchone()
            if not media:
                return []
            for episode in episodes:
                conn.execute(
                    """
                    INSERT INTO episode (id, media_id, season_number, episode_number, title, synopsis, watched,
                                         air_date, runtime, still_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode.get("id") or str(uuid.uuid4()),
                        media_id,
                        episode["season_number"],
                        episode["episode_number"],
                        episode["title"],
                        episode.get("synopsis"),
                        int(bool(episode.get("watched", False))),
                        episode.get("air_date"),
                        episode.get("runtime"),
                        episode.get("still_url"),
                    ),
                )
            self._recalculate_series_status(conn, media_id)
        return self._list_episodes_sync(media_id)

    def _upsert_episodes_sync(self, media_id: str, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Refresh TMDB episode metadata without ever resetting local watch history."""
        with sqlite3.connect(self.db_path) as conn:
            media = conn.execute(
                "SELECT id FROM media WHERE id = ? AND substr(type, 1, 1) = 'S' AND substr(type, -3) = 'rie'", (media_id,)
            ).fetchone()
            if not media:
                return []
            for episode in episodes:
                conn.execute(
                    """
                    INSERT INTO episode (id, media_id, season_number, episode_number, title, synopsis, watched,
                                         air_date, runtime, still_url)
                    VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    ON CONFLICT(media_id, season_number, episode_number) DO UPDATE SET
                        title = excluded.title,
                        synopsis = excluded.synopsis,
                        air_date = excluded.air_date,
                        runtime = excluded.runtime,
                        still_url = excluded.still_url
                    """,
                    (
                        str(uuid.uuid4()), media_id, episode["season_number"],
                        episode["episode_number"], episode["title"], episode.get("synopsis"),
                        episode.get("air_date"), episode.get("runtime"), episode.get("still_url"),
                    ),
                )
            self._recalculate_series_status(conn, media_id)
        return self._list_episodes_sync(media_id)

    def _save_series_metadata_sync(
        self, media_id: str, seasons: List[Dict[str, Any]], info: Dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            for season in seasons:
                conn.execute(
                    """
                    INSERT INTO series_season (media_id, season_number, name, overview, poster_url, air_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(media_id, season_number) DO UPDATE SET
                        name = excluded.name, overview = excluded.overview,
                        poster_url = excluded.poster_url, air_date = excluded.air_date
                    """,
                    (media_id, season["season_number"], season.get("name"), season.get("overview"),
                     season.get("poster_url"), season.get("air_date")),
                )
            conn.execute(
                """
                INSERT INTO series_info (
                    media_id, tmdb_status, first_air_date, last_air_date, number_of_seasons,
                    vote_average, next_air_date, next_season_number, next_episode_number,
                    next_episode_name, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    tmdb_status = excluded.tmdb_status, first_air_date = excluded.first_air_date,
                    last_air_date = excluded.last_air_date, number_of_seasons = excluded.number_of_seasons,
                    vote_average = excluded.vote_average, next_air_date = excluded.next_air_date,
                    next_season_number = excluded.next_season_number,
                    next_episode_number = excluded.next_episode_number,
                    next_episode_name = excluded.next_episode_name, updated_at = excluded.updated_at
                """,
                (media_id, info.get("tmdb_status"), info.get("first_air_date"), info.get("last_air_date"),
                 info.get("number_of_seasons"), info.get("vote_average"), info.get("next_air_date"),
                 info.get("next_season_number"), info.get("next_episode_number"),
                 info.get("next_episode_name"), now),
            )

    def _get_series_metadata_sync(self, media_id: str) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            info = conn.execute("SELECT * FROM series_info WHERE media_id = ?", (media_id,)).fetchone()
            seasons = conn.execute(
                "SELECT season_number, name, overview, poster_url, air_date FROM series_season "
                "WHERE media_id = ? ORDER BY season_number",
                (media_id,),
            ).fetchall()
        return {
            "info": dict(info) if info else None,
            "seasons": [dict(row) for row in seasons],
        }

    def _list_episode_playback_sync(self, media_id: str, user_id: str) -> Dict[tuple, Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT season_number, episode_number, percent, played, last_played_at
                FROM playback_progress
                WHERE backstage_user_id = ? AND media_id = ?
                  AND season_number IS NOT NULL AND episode_number IS NOT NULL
                """,
                (user_id, media_id),
            ).fetchall()
        return {(row["season_number"], row["episode_number"]): dict(row) for row in rows}

    def _set_user_season_watched_sync(
        self, media_id: str, season_number: int, user_id: str, watched: bool,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT episode.id FROM episode
                JOIN media ON media.id = episode.media_id
                WHERE episode.media_id = ? AND episode.season_number = ?
                  AND substr(media.type, 1, 1) = 'S' AND substr(media.type, -3) = 'rie'
                """,
                (media_id, season_number),
            ).fetchall()
            for (episode_id,) in rows:
                conn.execute(
                    """
                    INSERT INTO user_episode_state (backstage_user_id, episode_id, watched, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(backstage_user_id, episode_id) DO UPDATE SET
                        watched = excluded.watched, updated_at = excluded.updated_at
                    """,
                    (user_id, episode_id, int(watched), now),
                )
        return len(rows)

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
                SELECT id, media_id, season_number, episode_number, title, synopsis, watched,
                       air_date, runtime, still_url
                FROM episode WHERE id = ?
                """,
                (episode_id,),
            ).fetchone()
        return self._row_to_episode(row)

    def _set_user_episode_watched_sync(
        self, episode_id: str, user_id: str, watched: bool,
    ) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            episode = conn.execute(
                """
                SELECT episode.id
                FROM episode
                JOIN media ON media.id = episode.media_id
                WHERE episode.id = ? AND substr(media.type, 1, 1) = 'S' AND substr(media.type, -3) = 'rie'
                """,
                (episode_id,),
            ).fetchone()
            if not episode:
                return None
            conn.execute(
                """
                INSERT INTO user_episode_state (backstage_user_id, episode_id, watched, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(backstage_user_id, episode_id) DO UPDATE SET
                    watched = excluded.watched,
                    updated_at = excluded.updated_at
                """,
                (user_id, episode_id, int(watched), now),
            )
        return self._get_episode_for_user_sync(episode_id, user_id)

    def _get_episode_for_user_sync(self, episode_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT episode.id, episode.media_id, episode.season_number,
                       episode.episode_number, episode.title, episode.synopsis,
                       episode.air_date, episode.runtime, episode.still_url,
                       COALESCE(user_episode_state.watched, 0) AS watched
                FROM episode
                JOIN media ON media.id = episode.media_id
                LEFT JOIN user_episode_state
                  ON user_episode_state.episode_id = episode.id
                 AND user_episode_state.backstage_user_id = ?
                WHERE episode.id = ? AND substr(media.type, 1, 1) = 'S' AND substr(media.type, -3) = 'rie'
                """,
                (user_id, episode_id),
            ).fetchone()
        return self._row_to_episode(row) if row else None

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

    def _list_rentals_for_media_sync(self, media_id: str) -> List[Rental]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM media_rentals WHERE media_id = ? ORDER BY created_at DESC",
                (media_id,),
            ).fetchall()
        return [self._row_to_rental(row) for row in rows]

    def _count_rental_slots_sync(self, user_id: str) -> Dict[str, int]:
        """Split a user's active rentals into used slots and queued (waiting) requests."""
        active = ", ".join("?" for _ in _ACTIVE_RENTAL_STATES)
        waiting = ", ".join("?" for _ in _WAITING_DOWNLOAD_STATES)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT "
                f"COALESCE(SUM(CASE WHEN r.status = 'requested' AND (a.state IS NULL OR a.state IN ({waiting})) THEN 1 ELSE 0 END), 0), "
                "COUNT(*) "
                "FROM media_rentals r LEFT JOIN media_availability a ON a.media_id = r.media_id "
                f"WHERE r.backstage_user_id = ? AND r.status IN ({active})",
                (*_WAITING_DOWNLOAD_STATES, user_id, *_ACTIVE_RENTAL_STATES),
            ).fetchone()
        queued, total = int(row[0]), int(row[1])
        return {"in_use": total - queued, "queued": queued}

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

    def _find_active_rental_sync(
        self, user_id: str, media_id: str, season_number: Optional[int] = None,
    ) -> Optional[Rental]:
        placeholders = ", ".join("?" for _ in _ACTIVE_RENTAL_STATES)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM media_rentals WHERE backstage_user_id = ? AND media_id = ? "
                f"AND status IN ({placeholders}) AND season_number IS ?",
                (user_id, media_id, *_ACTIVE_RENTAL_STATES, season_number),
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

    def _expire_rentals_sync(self, now: datetime) -> int:
        """Close overdue temporary rentals; pending keep requests wait for the admin."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE media_rentals SET status = 'expired', updated_at = ? "
                "WHERE status = 'available' AND storage_policy = 'temporary' "
                "AND expires_at IS NOT NULL AND expires_at <= ?",
                (now.isoformat(), now.isoformat()),
            )
        return cursor.rowcount

    def _decide_rental_sync(self, rental_id: str, decision: str, admin_id: str, decided_at: datetime) -> Optional[Rental]:
        if decision not in {"accepted", "refused"}:
            raise ValueError("invalid rental decision")
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT status FROM media_rentals WHERE id = ?", (rental_id,)).fetchone()
            if not row:
                return None
            if decision == "refused" and row[0] != "keep_requested":
                raise ValueError("rental is not awaiting a conservation decision")
            if decision == "accepted" and row[0] not in {"available", "keep_requested"}:
                raise ValueError("rental is not available for permanent retention")
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

    def _revoke_rental_sync(self, rental_id: str, admin_id: str, decided_at: datetime) -> Optional[Rental]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT status FROM media_rentals WHERE id = ?", (rental_id,)).fetchone()
            if not row:
                return None
            if row[0] not in _ACTIVE_RENTAL_STATES:
                raise ValueError("rental is no longer active")
            conn.execute(
                "UPDATE media_rentals SET status = 'expired', keep_decision = 'refused', "
                "keep_requested_at = NULL, decided_by = ?, decided_at = ?, updated_at = ? WHERE id = ?",
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

    @staticmethod
    def _row_to_chat_message(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "author": {
                "id": row["author_id"],
                "display_name": row["author_name"],
                "avatar_url": row["author_avatar_url"],
            },
            "body": row["body"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload"]) if row["payload"] else None,
        }

    def _create_chat_message_sync(
        self, author_id: str, author_name: str, author_avatar_url: Optional[str], body: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "INSERT INTO chat_messages (author_id, author_name, author_avatar_url, body, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    author_id, author_name, author_avatar_url, body, created_at,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                ),
            )
            row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._row_to_chat_message(row)

    def _list_chat_messages_sync(self, after_id: Optional[int], limit: int) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if after_id is None:
                rows = conn.execute(
                    "SELECT * FROM chat_messages ORDER BY id DESC LIMIT ?", (limit,),
                ).fetchall()
                rows.reverse()
            else:
                rows = conn.execute(
                    "SELECT * FROM chat_messages WHERE id > ? ORDER BY id ASC LIMIT ?", (after_id, limit),
                ).fetchall()
        return [self._row_to_chat_message(row) for row in rows]

    async def create_chat_message(
        self, author_id: str, author_name: str, author_avatar_url: Optional[str], body: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._create_chat_message_sync, author_id, author_name, author_avatar_url, body, payload,
        )

    async def list_chat_messages(self, after_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_chat_messages_sync, after_id, limit)

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
                f"WHERE media_id = ? AND status IN ({placeholders}) AND rental_scope != 'season'",
                (available_at.isoformat(), expires_at.isoformat(), size_bytes, available_at.isoformat(), media_id, *active_states),
            )
        return cursor.rowcount

    def _mark_season_rentals_available_sync(
        self, media_id: str, season_numbers: List[int], available_at: datetime, expires_at: datetime,
    ) -> int:
        """A season rental becomes available once its whole season is on the server."""
        if not season_numbers:
            return 0
        seasons = ", ".join("?" for _ in season_numbers)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE media_rentals SET status = 'available', available_at = COALESCE(available_at, ?), "
                f"expires_at = COALESCE(expires_at, ?), updated_at = ? "
                f"WHERE media_id = ? AND rental_scope = 'season' AND status IN ('requested', 'downloading') "
                f"AND season_number IN ({seasons})",
                (available_at.isoformat(), expires_at.isoformat(), available_at.isoformat(), media_id, *season_numbers),
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

    async def storage_context(self, watched_since: datetime) -> Dict[str, Any]:
        return await asyncio.to_thread(self._storage_context_sync, watched_since)

    async def set_storage_protection(self, media_id: str, protected: bool) -> bool:
        return await asyncio.to_thread(self._set_storage_protection_sync, media_id, protected)

    async def record_storage_cleanup(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._record_storage_cleanup_sync, payload)

    async def list_storage_cleanup_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_storage_cleanup_log_sync, limit)

    async def upsert_user_media_state(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> UserMediaState:
        return await asyncio.to_thread(self._upsert_user_media_state_sync, user_id, media_id, fields)

    async def record_recommendation_event(self, event: RecommendationEvent) -> RecommendationEvent:
        return await asyncio.to_thread(self._record_recommendation_event_sync, event)

    async def list_recommendation_events(self, user_id: str) -> List[RecommendationEvent]:
        return await asyncio.to_thread(self._list_recommendation_events_sync, user_id)

    async def create_recommendation_session(
        self, session: RecommendationSession,
    ) -> RecommendationSession:
        return await asyncio.to_thread(self._create_recommendation_session_sync, session)

    async def create_recommendation_session_if_available(
        self, session: RecommendationSession, limit: int, day_start: Any,
    ) -> Optional[RecommendationSession]:
        return await asyncio.to_thread(
            self._create_recommendation_session_if_available_sync, session, limit, day_start,
        )

    async def get_recommendation_session(self, session_id: str) -> Optional[RecommendationSession]:
        return await asyncio.to_thread(self._get_recommendation_session_sync, session_id)

    async def update_recommendation_session(
        self, session_id: str, fields: Dict[str, Any],
    ) -> Optional[RecommendationSession]:
        return await asyncio.to_thread(self._update_recommendation_session_sync, session_id, fields)

    async def advance_recommendation_session(
        self, session_id: str, expected_question_count: int, preferences: Dict[str, Any],
    ) -> bool:
        return await asyncio.to_thread(
            self._advance_recommendation_session_sync, session_id, expected_question_count, preferences,
        )
    def count_recommendation_sessions_sync(self, user_id: str, day_start: Any) -> int:
        return self._count_recommendation_sessions_sync(user_id, day_start)

    def get_recommendation_usage_sync(self, session_id: str) -> List[Dict[str, Any]]:
        return self._get_recommendation_usage_sync(session_id)

    def record_recommendation_usage_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._record_recommendation_usage_sync(payload)

    def upsert_media_recommendation_preference_sync(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._upsert_media_recommendation_preference_sync(user_id, media_id, fields)

    async def count_recommendation_sessions(self, user_id: str, day_start: Any) -> int:
        return await asyncio.to_thread(self._count_recommendation_sessions_sync, user_id, day_start)

    async def get_recommendation_usage(self, session_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_recommendation_usage_sync, session_id)

    async def record_recommendation_usage(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._record_recommendation_usage_sync, payload)

    async def upsert_media_recommendation_preference(
        self, user_id: str, media_id: str, fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._upsert_media_recommendation_preference_sync, user_id, media_id, fields)

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

    async def list_episodes_for_user(self, media_id: str, user_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_episodes_for_user_sync, media_id, user_id)

    async def set_episode_watched(self, episode_id: str, watched: bool) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._set_episode_watched_sync, episode_id, watched)

    async def set_user_episode_watched(
        self, episode_id: str, user_id: str, watched: bool,
    ) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._set_user_episode_watched_sync, episode_id, user_id, watched)

    async def save_series_metadata(
        self, media_id: str, seasons: List[Dict[str, Any]], info: Dict[str, Any],
    ) -> None:
        await asyncio.to_thread(self._save_series_metadata_sync, media_id, seasons, info)

    async def get_series_metadata(self, media_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._get_series_metadata_sync, media_id)

    async def list_episode_playback(self, media_id: str, user_id: str) -> Dict[tuple, Dict[str, Any]]:
        return await asyncio.to_thread(self._list_episode_playback_sync, media_id, user_id)

    async def set_user_season_watched(
        self, media_id: str, season_number: int, user_id: str, watched: bool,
    ) -> int:
        return await asyncio.to_thread(
            self._set_user_season_watched_sync, media_id, season_number, user_id, watched,
        )

    async def series_progress(self, media_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._series_progress_sync, media_id)

    async def series_progress_for_user(self, media_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._series_progress_for_user_sync, media_id, user_id)

    async def get_availability(self, media_id: str) -> Optional[Availability]:
        return await asyncio.to_thread(self._get_availability_sync, media_id)

    async def create_rental(self, rental: Rental) -> Rental:
        return await asyncio.to_thread(self._create_rental_sync, rental)

    async def get_rental(self, rental_id: str) -> Optional[Rental]:
        return await asyncio.to_thread(self._get_rental_sync, rental_id)

    async def list_user_rentals(self, user_id: str) -> List[Rental]:
        return await asyncio.to_thread(self._list_user_rentals_sync, user_id)

    async def list_rentals_for_media(self, media_id: str) -> List[Rental]:
        return await asyncio.to_thread(self._list_rentals_for_media_sync, media_id)

    async def count_rental_slots(self, user_id: str) -> Dict[str, int]:
        return await asyncio.to_thread(self._count_rental_slots_sync, user_id)

    async def count_active_rentals(self, user_id: str) -> int:
        return await asyncio.to_thread(self._count_active_rentals_sync, user_id)

    async def active_temporary_bytes(self, user_id: Optional[str] = None) -> int:
        return await asyncio.to_thread(self._active_temporary_bytes_sync, user_id)

    async def find_active_rental(
        self, user_id: str, media_id: str, season_number: Optional[int] = None,
    ) -> Optional[Rental]:
        return await asyncio.to_thread(self._find_active_rental_sync, user_id, media_id, season_number)

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

    async def revoke_rental(self, rental_id: str, admin_id: str, decided_at: datetime) -> Optional[Rental]:
        return await asyncio.to_thread(self._revoke_rental_sync, rental_id, admin_id, decided_at)

    async def expire_rentals(self, now: datetime) -> int:
        return await asyncio.to_thread(self._expire_rentals_sync, now)

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

    async def mark_season_rentals_available(
        self, media_id: str, season_numbers: List[int], available_at: datetime, expires_at: datetime,
    ) -> int:
        return await asyncio.to_thread(
            self._mark_season_rentals_available_sync, media_id, season_numbers, available_at, expires_at,
        )

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


    # --- Journal « Vu », cache TMDB et listes partagées ---------------------

    _DIARY_ORDER = "ORDER BY watched_on IS NULL, watched_on DESC, created_at DESC"

    @staticmethod
    def _row_to_diary_entry(row: sqlite3.Row) -> DiaryEntry:
        data = dict(row)
        data["in_cinema"] = bool(data["in_cinema"])
        return DiaryEntry(**data)

    @staticmethod
    def _diary_values(fields: Dict[str, Any]) -> Dict[str, Any]:
        values = dict(fields)
        for key, value in list(values.items()):
            if isinstance(value, (date, datetime)):
                values[key] = value.isoformat()
            elif isinstance(value, bool):
                values[key] = int(value)
        return values

    def _upsert_tmdb_movie_sync(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        values = {
            "tmdb_id": int(movie["tmdb_id"]),
            "title": movie["title"],
            "year": movie.get("year"),
            "release_date": movie.get("release_date"),
            "poster_url": movie.get("poster_url"),
            "genres": json.dumps(list(movie.get("genres") or []), ensure_ascii=False),
            "fr_release_date": movie.get("fr_release_date"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        columns = list(values)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO tmdb_movie_cache ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                [values[column] for column in columns],
            )
        return self._get_tmdb_movies_sync([values["tmdb_id"]])[values["tmdb_id"]]

    def _get_tmdb_movies_sync(self, tmdb_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        ids = [int(tmdb_id) for tmdb_id in tmdb_ids]
        if not ids:
            return {}
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM tmdb_movie_cache WHERE tmdb_id IN ({', '.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        movies = {}
        for row in rows:
            movie = dict(row)
            movie["genres"] = json.loads(movie["genres"] or "[]")
            movies[movie["tmdb_id"]] = movie
        return movies

    def _create_diary_entry_sync(self, entry: DiaryEntry) -> DiaryEntry:
        values = self._diary_values(entry.model_dump())
        columns = list(values)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"INSERT INTO diary_entries ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [values[column] for column in columns],
            )
        return self._get_diary_entry_sync(entry.id)

    def _get_diary_entry_sync(self, entry_id: str) -> Optional[DiaryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM diary_entries WHERE id = ?", (entry_id,)).fetchone()
        return self._row_to_diary_entry(row) if row else None

    def _list_diary_entries_sync(self, user_id: str) -> List[DiaryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM diary_entries WHERE backstage_user_id = ? {self._DIARY_ORDER}",
                (user_id,),
            ).fetchall()
        return [self._row_to_diary_entry(row) for row in rows]

    def _update_diary_entry_sync(self, entry_id: str, fields: Dict[str, Any]) -> Optional[DiaryEntry]:
        allowed = {"watched_on", "rating", "review", "in_cinema", "source"}
        values = self._diary_values({k: v for k, v in fields.items() if k in allowed})
        values["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{column} = ?" for column in values)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE diary_entries SET {assignments} WHERE id = ?",
                [*values.values(), entry_id],
            )
        if cursor.rowcount == 0:
            return None
        return self._get_diary_entry_sync(entry_id)

    def _delete_diary_entry_sync(self, entry_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM diary_entries WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def _latest_diary_entry_sync(self, user_id: str, tmdb_id: int) -> Optional[DiaryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT * FROM diary_entries WHERE backstage_user_id = ? AND tmdb_id = ? "
                f"{self._DIARY_ORDER} LIMIT 1",
                (user_id, int(tmdb_id)),
            ).fetchone()
        return self._row_to_diary_entry(row) if row else None

    def _list_diary_tmdb_ids_sync(self, user_id: str) -> set:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT tmdb_id FROM diary_entries WHERE backstage_user_id = ?",
                (user_id,),
            ).fetchall()
        return {int(row[0]) for row in rows}

    @staticmethod
    def _row_to_film_list(row: sqlite3.Row) -> FilmList:
        return FilmList(**{key: row[key] for key in ("id", "name", "created_by", "created_at")})

    def _create_film_list_sync(self, name: str, created_by: str) -> FilmList:
        film_list = FilmList(
            id=str(uuid.uuid4()), name=name, created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO film_lists (id, name, created_by, created_at) VALUES (?, ?, ?, ?)",
                (film_list.id, film_list.name, film_list.created_by, film_list.created_at.isoformat()),
            )
        return film_list

    def _list_film_lists_sync(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT l.*, COUNT(i.tmdb_id) AS item_count FROM film_lists l "
                "LEFT JOIN film_list_items i ON i.list_id = l.id "
                "GROUP BY l.id ORDER BY l.created_at"
            ).fetchall()
        return [
            {**self._row_to_film_list(row).model_dump(), "item_count": row["item_count"]}
            for row in rows
        ]

    def _get_film_list_sync(self, list_id: str) -> Optional[FilmList]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM film_lists WHERE id = ?", (list_id,)).fetchone()
        return self._row_to_film_list(row) if row else None

    def _rename_film_list_sync(self, list_id: str, name: str) -> Optional[FilmList]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("UPDATE film_lists SET name = ? WHERE id = ?", (name, list_id))
        return self._get_film_list_sync(list_id) if cursor.rowcount else None

    def _delete_film_list_sync(self, list_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM film_list_items WHERE list_id = ?", (list_id,))
            cursor = conn.execute("DELETE FROM film_lists WHERE id = ?", (list_id,))
        return cursor.rowcount > 0

    def _add_film_list_item_sync(self, list_id: str, tmdb_id: int, added_by: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO film_list_items (list_id, tmdb_id, added_by, added_at) "
                "VALUES (?, ?, ?, ?)",
                (list_id, int(tmdb_id), added_by, datetime.now(timezone.utc).isoformat()),
            )
        return cursor.rowcount > 0

    def _remove_film_list_item_sync(self, list_id: str, tmdb_id: int) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM film_list_items WHERE list_id = ? AND tmdb_id = ?",
                (list_id, int(tmdb_id)),
            )
        return cursor.rowcount > 0

    def _list_film_list_items_sync(self, list_id: str) -> List[FilmListItem]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM film_list_items WHERE list_id = ? ORDER BY added_at DESC",
                (list_id,),
            ).fetchall()
        return [FilmListItem(**dict(row)) for row in rows]

    async def upsert_tmdb_movie(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._upsert_tmdb_movie_sync, movie)

    async def get_tmdb_movies(self, tmdb_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        return await asyncio.to_thread(self._get_tmdb_movies_sync, tmdb_ids)

    async def create_diary_entry(self, entry: DiaryEntry) -> DiaryEntry:
        return await asyncio.to_thread(self._create_diary_entry_sync, entry)

    async def get_diary_entry(self, entry_id: str) -> Optional[DiaryEntry]:
        return await asyncio.to_thread(self._get_diary_entry_sync, entry_id)

    async def list_diary_entries(self, user_id: str) -> List[DiaryEntry]:
        return await asyncio.to_thread(self._list_diary_entries_sync, user_id)

    async def update_diary_entry(self, entry_id: str, fields: Dict[str, Any]) -> Optional[DiaryEntry]:
        return await asyncio.to_thread(self._update_diary_entry_sync, entry_id, fields)

    async def delete_diary_entry(self, entry_id: str) -> bool:
        return await asyncio.to_thread(self._delete_diary_entry_sync, entry_id)

    async def latest_diary_entry(self, user_id: str, tmdb_id: int) -> Optional[DiaryEntry]:
        return await asyncio.to_thread(self._latest_diary_entry_sync, user_id, tmdb_id)

    async def list_diary_tmdb_ids(self, user_id: str) -> set:
        return await asyncio.to_thread(self._list_diary_tmdb_ids_sync, user_id)

    async def create_film_list(self, name: str, created_by: str) -> FilmList:
        return await asyncio.to_thread(self._create_film_list_sync, name, created_by)

    async def list_film_lists(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_film_lists_sync)

    async def get_film_list(self, list_id: str) -> Optional[FilmList]:
        return await asyncio.to_thread(self._get_film_list_sync, list_id)

    async def rename_film_list(self, list_id: str, name: str) -> Optional[FilmList]:
        return await asyncio.to_thread(self._rename_film_list_sync, list_id, name)

    async def delete_film_list(self, list_id: str) -> bool:
        return await asyncio.to_thread(self._delete_film_list_sync, list_id)

    async def add_film_list_item(self, list_id: str, tmdb_id: int, added_by: str) -> bool:
        return await asyncio.to_thread(self._add_film_list_item_sync, list_id, tmdb_id, added_by)

    async def remove_film_list_item(self, list_id: str, tmdb_id: int) -> bool:
        return await asyncio.to_thread(self._remove_film_list_item_sync, list_id, tmdb_id)

    async def list_film_list_items(self, list_id: str) -> List[FilmListItem]:
        return await asyncio.to_thread(self._list_film_list_items_sync, list_id)
