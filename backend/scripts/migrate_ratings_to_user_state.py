"""One-time migration: carry media.rating / media.status verdicts into
per-user user_media_state, the only table the recommendation engine reads.

Backstage's V2 catalogue keeps ratings and watch status on `media` for
display, but `build_taste_profile` only reads `user_media_state` — so every
rating and status saved before that split (and every rating saved directly
through routes that only ever touched `media`) is invisible to the
recommendation engine until it is copied across once.

Safe to re-run: re-migrating overwrites only the rating/status/watchlist
fields for a given user+media pair with the current value in `media`, and
never touches other user_media_state fields (is_favorite, review, etc.).

Run a preview first with ``python -m backend.scripts.migrate_ratings_to_user_state``.
Add ``--apply`` only after checking its output.
"""
from __future__ import annotations

import argparse
import asyncio

from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.store import MediaStore

_DONE_STATUSES = {"Terminé", "Terminée", "A revoir"}
_LEGACY_WATCHLIST_STATUS = "watchlist"


def _has_parseable_rating(rating: str | None) -> bool:
    if not rating or not rating.strip():
        return False
    text = rating.strip()
    if "⭐" in text:
        return True
    try:
        float(text)
        return True
    except ValueError:
        return False


async def migrate_ratings_to_user_state(
    store: MediaStore, user_id: str, *, apply: bool,
) -> dict[str, int]:
    """Preview or apply media.rating/status -> user_media_state for one user."""
    summary = {"migrated": 0, "watchlisted": 0, "skipped": 0}
    for media in await store.fetch_all():
        has_rating = _has_parseable_rating(media.rating)
        is_done = media.status in _DONE_STATUSES
        is_legacy_watchlist = media.status == _LEGACY_WATCHLIST_STATUS
        if not (has_rating or is_done or is_legacy_watchlist):
            summary["skipped"] += 1
            continue

        fields: dict[str, object] = {}
        if has_rating:
            fields["rating"] = media.rating
        if is_done:
            fields["status"] = media.status
        if is_legacy_watchlist:
            fields["is_watchlist"] = True
            summary["watchlisted"] += 1

        if apply:
            await store.upsert_user_media_state(user_id, media.id, fields)
        summary["migrated"] += 1
    return summary


def resolve_user_id(auth_store: AuthStore, requested: str | None) -> str:
    users = auth_store.list_users()
    if requested:
        if not any(user["id"] == requested for user in users):
            raise SystemExit(f"Utilisateur introuvable : {requested}")
        return requested
    if len(users) == 1:
        return users[0]["id"]
    raise SystemExit(
        "Plusieurs comptes existent, précisez --user-id parmi :\n"
        + "\n".join(f"  {user['id']}  {user['display_name']} <{user['email']}>" for user in users)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copie les notes/statuts déjà saisis dans media vers user_media_state, "
            "seule table lue par le moteur de recommandation."
        ),
    )
    parser.add_argument("--user-id", help="Identifiant Backstage cible. Requis s'il y a plusieurs comptes.")
    parser.add_argument("--apply", action="store_true", help="Écrit les changements dans SQLite.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    store = MediaStore(Config.DB_PATH)
    store.init_schema()
    auth_store = AuthStore(Config.DB_PATH)
    auth_store.init_schema()
    user_id = resolve_user_id(auth_store, args.user_id)
    summary = await migrate_ratings_to_user_state(store, user_id, apply=args.apply)
    mode = "appliquée" if args.apply else "prévisualisée"
    print(
        f"Migration {mode} pour l'utilisateur {user_id} : "
        f"{summary['migrated']} médias concernés (dont {summary['watchlisted']} passés en watchlist), "
        f"{summary['skipped']} ignorés (aucun verdict)."
    )
    if not args.apply:
        print("Relancez avec --apply pour écrire les changements.")


if __name__ == "__main__":
    asyncio.run(main())
