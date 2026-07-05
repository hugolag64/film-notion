"""Persistance locale des médias (SQLite), remplace Notion comme source de vérité."""
import asyncio
import json
import sqlite3
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from backend.core.models import Media

_COLUMNS = [
    "id", "title", "type", "status", "support", "rating", "release_date",
    "director", "categories", "synopsis", "tags", "review", "tmdb_ok", "cover_url",
]

_LIST_FIELDS = {"categories", "tags"}


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
                    cover_url TEXT
                )
                """
            )

    @staticmethod
    def _row_to_media(row: sqlite3.Row) -> Media:
        data = dict(row)
        for field in _LIST_FIELDS:
            data[field] = json.loads(data[field]) if data[field] else []
        data["tmdb_ok"] = bool(data["tmdb_ok"])
        if data["release_date"]:
            data["release_date"] = date.fromisoformat(data["release_date"])
        return Media(**data)

    @staticmethod
    def _encode(field: str, value: Any) -> Any:
        if field in _LIST_FIELDS:
            return json.dumps(value or [])
        if field == "release_date" and value is not None:
            return value.isoformat() if isinstance(value, date) else value
        if field == "tmdb_ok":
            return int(bool(value))
        return value

    def _fetch_all_sync(self) -> List[Media]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"SELECT {', '.join(_COLUMNS)} FROM media").fetchall()
        return [self._row_to_media(row) for row in rows]

    def _fetch_one_sync(self, media_id: str) -> Optional[Media]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM media WHERE id = ?", (media_id,)
            ).fetchone()
        return self._row_to_media(row) if row else None

    def _create_sync(self, fields: Dict[str, Any]) -> Media:
        media_id = fields.get("id") or str(uuid.uuid4())
        values = {col: fields.get(col) for col in _COLUMNS if col != "id"}
        values["id"] = media_id

        with sqlite3.connect(self.db_path) as conn:
            placeholders = ", ".join("?" for _ in _COLUMNS)
            conn.execute(
                f"INSERT INTO media ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                [self._encode(col, values[col]) for col in _COLUMNS],
            )
        return self._fetch_one_sync(media_id)

    def _update_sync(self, media_id: str, fields: Dict[str, Any]) -> bool:
        if not fields:
            return self._fetch_one_sync(media_id) is not None
        filtered_fields = {col: fields.get(col) for col in _COLUMNS if col != "id" and col in fields}
        if not filtered_fields:
            return self._fetch_one_sync(media_id) is not None
        set_clause = ", ".join(f"{col} = ?" for col in filtered_fields)
        values = [self._encode(col, val) for col, val in filtered_fields.items()]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                f"UPDATE media SET {set_clause} WHERE id = ?", [*values, media_id]
            )
            return cursor.rowcount > 0

    async def fetch_all(self) -> List[Media]:
        return await asyncio.to_thread(self._fetch_all_sync)

    async def fetch_one(self, media_id: str) -> Optional[Media]:
        return await asyncio.to_thread(self._fetch_one_sync, media_id)

    async def create(self, fields: Dict[str, Any]) -> Media:
        return await asyncio.to_thread(self._create_sync, fields)

    async def update(self, media_id: str, fields: Dict[str, Any]) -> bool:
        return await asyncio.to_thread(self._update_sync, media_id, fields)
