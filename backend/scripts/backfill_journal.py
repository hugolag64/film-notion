"""One-time migration: seed the « Vu » journal with every film already marked
as seen in the library.

Sources, per user and per film with a TMDB id:
- the user's own `user_media_state` row;
- for the catalogue owner only (the first administrator), `media.status` /
  `media.rating` when they have no personal row — the same fallback as the
  library display.

A film counts as seen when its status is « Terminé », « Terminée » or
« A revoir », or when it carries a rating. Entries have no date (the watch
date was never recorded) and `source="backfill"`.

Safe to re-run: a (user, film) pair that already has a journal entry is
skipped.

Preview with ``python -m backend.scripts.backfill_journal``; add ``--apply``
only after checking its output.
"""
from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import Counter
from datetime import datetime, timezone

from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.mapping import is_series
from backend.core.models import DiaryEntry
from backend.core.recommendations import _rating_value
from backend.core.store import MediaStore

_SEEN_STATUSES = {"Terminé", "Terminée", "A revoir"}


def _catalogue_owner_id(auth_store: AuthStore) -> str | None:
    for user in auth_store.list_users():
        if user["role"] == "admin":
            return user["id"]
    return None


def _journal_rating(raw: str | None) -> float | None:
    value = _rating_value(raw)
    if value is None:
        return None
    return min(5.0, max(0.5, round(value * 2) / 2))


def _entry_for(user_id: str, tmdb_id: int, status, raw_rating, review) -> DiaryEntry | None:
    has_rating = bool(raw_rating and str(raw_rating).strip())
    if status not in _SEEN_STATUSES and not has_rating:
        return None
    rating = _journal_rating(raw_rating) if has_rating else None
    if has_rating and rating is None:
        note = f"Note d'origine : {str(raw_rating).strip()}"
        review = f"{review}\n{note}" if review else note
    now = datetime.now(timezone.utc)
    return DiaryEntry(
        id=str(uuid.uuid4()), backstage_user_id=user_id, tmdb_id=tmdb_id,
        watched_on=None, rating=rating, review=review or None,
        source="backfill", created_at=now, updated_at=now,
    )


async def plan_backfill(media_store: MediaStore, auth_store: AuthStore) -> list[DiaryEntry]:
    films = [m for m in await media_store.fetch_all() if m.tmdb_id and not is_series(m.type)]
    owner_id = _catalogue_owner_id(auth_store)
    entries: list[DiaryEntry] = []
    for user in auth_store.list_users():
        user_id = user["id"]
        states = {state.media_id: state for state in await media_store.list_user_media_states(user_id)}
        already = await media_store.list_diary_tmdb_ids(user_id)
        for media in films:
            if media.tmdb_id in already:
                continue
            state = states.get(media.id)
            if state is not None:
                entry = _entry_for(user_id, media.tmdb_id, state.status, state.rating, state.review)
            elif user_id == owner_id:
                entry = _entry_for(user_id, media.tmdb_id, media.status, media.rating, media.review)
            else:
                entry = None
            if entry is not None:
                entries.append(entry)
                already.add(media.tmdb_id)
    return entries


async def apply_backfill(media_store: MediaStore, entries: list[DiaryEntry]) -> int:
    await _cache_library_movies(media_store, {entry.tmdb_id for entry in entries})
    for entry in entries:
        await media_store.create_diary_entry(entry)
    return len(entries)


async def _cache_library_movies(media_store: MediaStore, tmdb_ids: set[int]) -> None:
    """The journal shows title and poster from the TMDB cache: fill it from the
    library sheets so the migration needs no TMDB call."""
    cached = await media_store.get_tmdb_movies(list(tmdb_ids))
    for media in await media_store.fetch_all():
        if media.tmdb_id not in tmdb_ids or media.tmdb_id in cached or is_series(media.type):
            continue
        await media_store.upsert_tmdb_movie({
            "tmdb_id": media.tmdb_id,
            "title": media.title,
            "year": media.release_date.year if media.release_date else None,
            "release_date": media.release_date.isoformat() if media.release_date else None,
            "poster_url": media.cover_url,
            "genres": list(media.categories or []),
        })
        cached[media.tmdb_id] = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reprend dans le journal « Vu » les films déjà marqués vus ou notés.",
    )
    parser.add_argument("--apply", action="store_true", help="Écrit les entrées dans SQLite.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    media_store = MediaStore(Config.DB_PATH)
    media_store.init_schema()
    auth_store = AuthStore(Config.DB_PATH)
    auth_store.init_schema()
    entries = await plan_backfill(media_store, auth_store)
    names = {user["id"]: user["display_name"] for user in auth_store.list_users()}
    titles = {m.tmdb_id: m.title for m in await media_store.fetch_all() if m.tmdb_id}
    per_user = Counter(entry.backstage_user_id for entry in entries)
    for user_id, count in per_user.items():
        sample = [titles.get(e.tmdb_id, str(e.tmdb_id)) for e in entries if e.backstage_user_id == user_id][:10]
        print(f"{names.get(user_id, user_id)} : {count} films — {', '.join(sample)}")
    if args.apply:
        written = await apply_backfill(media_store, entries)
        print(f"Reprise appliquée : {written} entrées créées.")
    else:
        print(f"Aperçu : {len(entries)} entrées à créer. Relancez avec --apply pour les écrire.")


if __name__ == "__main__":
    asyncio.run(main())
