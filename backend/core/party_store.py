"""Stockage SQLite des soirées film : soirée, partants, propositions et votes."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

ACTIVE_STATUSES = ("joining", "voting")


def create_party_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS parties (
            id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            starter_id TEXT NOT NULL,
            starter_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            launched_at TEXT,
            closed_at TEXT,
            winner_tmdb_id INTEGER,
            message_id INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS party_members (
            party_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            display_name TEXT NOT NULL,
            answers TEXT,
            late INTEGER NOT NULL DEFAULT 0,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (party_id, user_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS party_proposals (
            party_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            tmdb_id INTEGER,
            title TEXT NOT NULL,
            poster_url TEXT,
            reason TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL,
            site_id INTEGER,
            showtime TEXT,
            PRIMARY KEY (party_id, rank)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS party_votes (
            party_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            value INTEGER NOT NULL,
            PRIMARY KEY (party_id, user_id, rank)
        )
        """
    )


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _party(row: sqlite3.Row) -> Dict[str, Any]:
    party = dict(row)
    for key in ("created_at", "launched_at", "closed_at"):
        party[key] = _dt(party[key])
    return party


class PartyStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_party_sync(self, party_id, mode, starter_id, starter_name, created_at) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO parties (id, mode, status, starter_id, starter_name, created_at) VALUES (?, ?, 'joining', ?, ?, ?)",
                (party_id, mode, starter_id, starter_name, _iso(created_at)),
            )

    def _get_party_sync(self, party_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM parties WHERE id = ?", (party_id,)).fetchone()
        return _party(row) if row else None

    def _active_party_sync(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM parties WHERE status IN (?, ?) ORDER BY created_at DESC, rowid DESC LIMIT 1",
                ACTIVE_STATUSES,
            ).fetchone()
        return _party(row) if row else None

    def _set_status_sync(self, party_id, status, at, winner_tmdb_id) -> bool:
        column = "launched_at" if status == "voting" else "closed_at"
        # Le vote ne s'ouvre qu'une fois : deux « On lance » simultanés n'en lancent qu'un.
        sources = ("joining", "joining") if status == "voting" else ACTIVE_STATUSES
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE parties SET status = ?, {column} = ?, winner_tmdb_id = COALESCE(?, winner_tmdb_id) "
                "WHERE id = ? AND status IN (?, ?)",
                (status, _iso(at), winner_tmdb_id, party_id, *sources),
            )
            return cursor.rowcount == 1

    def _set_message_id_sync(self, party_id, message_id) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE parties SET message_id = ? WHERE id = ?", (message_id, party_id))

    def _add_member_sync(self, party_id, user_id, display_name, joined_at, late) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO party_members (party_id, user_id, display_name, late, joined_at) VALUES (?, ?, ?, ?, ?)",
                (party_id, user_id, display_name, int(late), _iso(joined_at)),
            )

    def _set_answers_sync(self, party_id, user_id, answers) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE party_members SET answers = ? WHERE party_id = ? AND user_id = ?",
                (json.dumps(answers), party_id, user_id),
            )

    def _list_members_sync(self, party_id) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, display_name, answers, late, joined_at FROM party_members WHERE party_id = ? ORDER BY joined_at, rowid",
                (party_id,),
            ).fetchall()
        return [
            {
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "answers": json.loads(row["answers"]) if row["answers"] else None,
                "late": bool(row["late"]),
                "joined_at": _dt(row["joined_at"]),
            }
            for row in rows
        ]

    def _replace_proposals_sync(self, party_id, proposals) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM party_proposals WHERE party_id = ?", (party_id,))
            conn.executemany(
                "INSERT INTO party_proposals (party_id, rank, tmdb_id, title, poster_url, reason, source, site_id, showtime) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        party_id, p["rank"], p.get("tmdb_id"), p["title"], p.get("poster_url"), p.get("reason") or "",
                        p["source"], p.get("site_id"), json.dumps(p["showtime"]) if p.get("showtime") else None,
                    )
                    for p in proposals
                ],
            )

    def _list_proposals_sync(self, party_id) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT rank, tmdb_id, title, poster_url, reason, source, site_id, showtime FROM party_proposals "
                "WHERE party_id = ? ORDER BY rank",
                (party_id,),
            ).fetchall()
        return [{**dict(row), "showtime": json.loads(row["showtime"]) if row["showtime"] else None} for row in rows]

    def _set_vote_sync(self, party_id, user_id, rank, value) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO party_votes (party_id, user_id, rank, value) VALUES (?, ?, ?, ?)",
                (party_id, user_id, rank, value),
            )

    def _list_votes_sync(self, party_id) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_id, rank, value FROM party_votes WHERE party_id = ? ORDER BY user_id, rank", (party_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # --- Enveloppes asynchrones ------------------------------------------

    async def create_party(self, party_id: str, mode: str, starter_id: str, starter_name: str, created_at: datetime) -> None:
        await asyncio.to_thread(self._create_party_sync, party_id, mode, starter_id, starter_name, created_at)

    async def get_party(self, party_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._get_party_sync, party_id)

    async def active_party(self) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(self._active_party_sync)

    async def set_status(
        self, party_id: str, status: str, *, at: Optional[datetime] = None, winner_tmdb_id: Optional[int] = None,
    ) -> bool:
        return await asyncio.to_thread(self._set_status_sync, party_id, status, at, winner_tmdb_id)

    async def set_message_id(self, party_id: str, message_id: int) -> None:
        await asyncio.to_thread(self._set_message_id_sync, party_id, message_id)

    async def add_member(self, party_id: str, user_id: str, display_name: str, joined_at: datetime, late: bool) -> None:
        await asyncio.to_thread(self._add_member_sync, party_id, user_id, display_name, joined_at, late)

    async def set_answers(self, party_id: str, user_id: str, answers: dict) -> None:
        await asyncio.to_thread(self._set_answers_sync, party_id, user_id, answers)

    async def list_members(self, party_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_members_sync, party_id)

    async def replace_proposals(self, party_id: str, proposals: List[dict]) -> None:
        await asyncio.to_thread(self._replace_proposals_sync, party_id, proposals)

    async def list_proposals(self, party_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_proposals_sync, party_id)

    async def set_vote(self, party_id: str, user_id: str, rank: int, value: int) -> None:
        await asyncio.to_thread(self._set_vote_sync, party_id, user_id, rank, value)

    async def list_votes(self, party_id: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._list_votes_sync, party_id)
