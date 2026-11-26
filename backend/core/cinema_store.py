"""Stockage SQLite du cinéma : films du site, séances, rappels, état, jetons d'agenda.

Les dates/heures locales (La Réunion) sont stockées naïves au format ISO.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.core.cinema_site import FilmDetails, Showtime


def create_cinema_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cinema_films (
            site_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            poster_url TEXT,
            original_title TEXT,
            directors TEXT NOT NULL DEFAULT '[]',
            release_national TEXT,
            release_reunion TEXT,
            details_fetched_at TEXT,
            tmdb_id INTEGER,
            match_attempted_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cinema_showtimes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            starts_at TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '',
            booking_url TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_cinema_showtimes_starts ON cinema_showtimes(starts_at)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cinema_reminders (
            site_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (site_id, kind)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cinema_status (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_success_at TEXT,
            last_error TEXT,
            last_error_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_tokens (
            user_id TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat(timespec="minutes") if value is not None else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


class CinemaStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Films du site ---------------------------------------------------

    def _upsert_site_film_sync(self, site_id: int, title: str, url: str, poster_url: Optional[str]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cinema_films (site_id, title, url, poster_url) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(site_id) DO UPDATE SET title = excluded.title, url = excluded.url, "
                "poster_url = COALESCE(excluded.poster_url, cinema_films.poster_url)",
                (int(site_id), title, url, poster_url),
            )

    def _set_film_details_sync(self, site_id: int, details: FilmDetails, fetched_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE cinema_films SET original_title = ?, directors = ?, release_national = ?, "
                "release_reunion = ?, details_fetched_at = ? WHERE site_id = ?",
                (
                    details.original_title,
                    json.dumps(list(details.directors), ensure_ascii=False),
                    details.release_national.isoformat() if details.release_national else None,
                    details.release_reunion.isoformat() if details.release_reunion else None,
                    _iso(fetched_at),
                    int(site_id),
                ),
            )

    def _set_tmdb_match_sync(self, site_id: int, tmdb_id: Optional[int], attempted_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE cinema_films SET tmdb_id = ?, match_attempted_at = ? WHERE site_id = ?",
                (tmdb_id, _iso(attempted_at), int(site_id)),
            )

    def _get_site_films_sync(self) -> Dict[int, Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cinema_films").fetchall()
        films = {}
        for row in rows:
            film = dict(row)
            film["directors"] = json.loads(film["directors"] or "[]")
            film["match_attempted_at"] = _dt(film["match_attempted_at"])
            film["details_fetched_at"] = _dt(film["details_fetched_at"])
            films[film["site_id"]] = film
        return films

    # --- Séances ---------------------------------------------------------

    def _replace_showtimes_sync(self, showtimes: Dict[int, List[Showtime]]) -> None:
        rows = [
            (int(site_id), _iso(show.starts_at), show.version, show.booking_url)
            for site_id, shows in showtimes.items()
            for show in shows
        ]
        with self._connect() as conn:
            conn.execute("DELETE FROM cinema_showtimes")
            conn.executemany(
                "INSERT INTO cinema_showtimes (site_id, starts_at, version, booking_url) VALUES (?, ?, ?, ?)",
                rows,
            )

    def _list_showtimes_sync(self, start: datetime, end: Optional[datetime]) -> List[Dict[str, Any]]:
        query = "SELECT site_id, starts_at, version, booking_url FROM cinema_showtimes WHERE starts_at >= ?"
        params: list = [_iso(start)]
        if end is not None:
            query += " AND starts_at < ?"
            params.append(_iso(end))
        query += " ORDER BY starts_at, site_id, id"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {
                "site_id": row["site_id"],
                "starts_at": datetime.fromisoformat(row["starts_at"]),
                "version": row["version"],
                "booking_url": row["booking_url"],
            }
            for row in rows
        ]

    # --- Rappels et état ---------------------------------------------------

    def _sent_reminders_sync(self) -> set:
        with self._connect() as conn:
            rows = conn.execute("SELECT site_id, kind FROM cinema_reminders").fetchall()
        return {(row["site_id"], row["kind"]) for row in rows}

    def _record_reminder_sync(self, site_id: int, kind: str, sent_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO cinema_reminders (site_id, kind, sent_at) VALUES (?, ?, ?)",
                (int(site_id), kind, _iso(sent_at)),
            )

    def _record_success_sync(self, at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cinema_status (id, last_success_at) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET last_success_at = excluded.last_success_at",
                (_iso(at),),
            )

    def _record_failure_sync(self, at: datetime, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO cinema_status (id, last_error, last_error_at) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET last_error = excluded.last_error, "
                "last_error_at = excluded.last_error_at",
                (error, _iso(at)),
            )

    def _get_status_sync(self) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cinema_status WHERE id = 1").fetchone()
        if row is None:
            return {"last_success_at": None, "last_error": None, "last_error_at": None}
        return {
            "last_success_at": _dt(row["last_success_at"]),
            "last_error": row["last_error"],
            "last_error_at": _dt(row["last_error_at"]),
        }

    def _tracked_tmdb_ids_sync(self) -> set:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT tmdb_id FROM film_list_items").fetchall()
        return {int(row["tmdb_id"]) for row in rows}

    # --- Jetons d'agenda ---------------------------------------------------

    def _calendar_token_for_sync(self, user_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute("SELECT token FROM calendar_tokens WHERE user_id = ?", (user_id,)).fetchone()
        return row["token"] if row else None

    def _set_calendar_token_sync(self, user_id: str, token: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO calendar_tokens (user_id, token, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET token = excluded.token, created_at = excluded.created_at",
                (user_id, token, datetime.now(timezone.utc).isoformat()),
            )

    def _user_for_calendar_token_sync(self, token: str) -> Optional[str]:
        if not token:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT user_id FROM calendar_tokens WHERE token = ?", (token,)).fetchone()
        return row["user_id"] if row else None

    # --- Enveloppes asynchrones ------------------------------------------

    async def upsert_site_film(self, site_id: int, title: str, url: str, poster_url: Optional[str]) -> None:
        await asyncio.to_thread(self._upsert_site_film_sync, site_id, title, url, poster_url)

    async def set_film_details(self, site_id: int, details: FilmDetails, fetched_at: datetime) -> None:
        await asyncio.to_thread(self._set_film_details_sync, site_id, details, fetched_at)

    async def set_tmdb_match(self, site_id: int, tmdb_id: Optional[int], attempted_at: datetime) -> None:
        await asyncio.to_thread(self._set_tmdb_match_sync, site_id, tmdb_id, attempted_at)

    async def get_site_films(self) -> Dict[int, Dict[str, Any]]:
        return await asyncio.to_thread(self._get_site_films_sync)

    async def replace_showtimes(self, showtimes: Dict[int, List[Showtime]]) -> None:
        await asyncio.to_thread(self._replace_showtimes_sync, showtimes)

    async def list_showtimes(self, start: datetime, end: Optional[datetime] = None) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_showtimes_sync, start, end)

    async def sent_reminders(self) -> set:
        return await asyncio.to_thread(self._sent_reminders_sync)

    async def record_reminder(self, site_id: int, kind: str, sent_at: datetime) -> None:
        await asyncio.to_thread(self._record_reminder_sync, site_id, kind, sent_at)

    async def record_success(self, at: datetime) -> None:
        await asyncio.to_thread(self._record_success_sync, at)

    async def record_failure(self, at: datetime, error: str) -> None:
        await asyncio.to_thread(self._record_failure_sync, at, error)

    async def get_status(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._get_status_sync)

    async def tracked_tmdb_ids(self) -> set:
        return await asyncio.to_thread(self._tracked_tmdb_ids_sync)

    async def calendar_token_for(self, user_id: str) -> Optional[str]:
        return await asyncio.to_thread(self._calendar_token_for_sync, user_id)

    async def set_calendar_token(self, user_id: str, token: str) -> None:
        await asyncio.to_thread(self._set_calendar_token_sync, user_id, token)

    async def user_for_calendar_token(self, token: str) -> Optional[str]:
        return await asyncio.to_thread(self._user_for_calendar_token_sync, token)
