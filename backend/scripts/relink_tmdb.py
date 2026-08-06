"""Safely associate local Backstage media with TMDB in batch.

Run a preview first with ``python -m backend.scripts.relink_tmdb``. Add
``--apply`` only after checking its output. Uncertain items are written to a
CSV report for manual association through Backstage.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Any, Dict

from backend.config import Config
from backend.core.mapping import is_series
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient
from backend.core.tmdb_relink import build_relink_updates, result_year, select_confident_match


def _candidate_text(candidates: list[Dict[str, Any]]) -> str:
    return " | ".join(
        f"{candidate.get('id')}: {candidate.get('title') or candidate.get('name') or 'Sans titre'} "
        f"({result_year(candidate) or '?'})"
        for candidate in candidates
    )


def _write_report(report_path: Path, rows: list[Dict[str, str]]) -> None:
    with report_path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(
            report,
            fieldnames=["media_id", "title", "type", "year", "reason", "candidates"],
        )
        writer.writeheader()
        writer.writerows(rows)


async def relink_missing_tmdb_ids(
    store: MediaStore,
    tmdb: Any,
    *,
    apply: bool,
    report_path: Path,
) -> Dict[str, int]:
    """Preview or apply confident TMDB associations and export all other cases."""
    summary = {"linked": 0, "to_review": 0, "already_linked": 0}
    report_rows: list[Dict[str, str]] = []

    for media in await store.fetch_all():
        if media.tmdb_id:
            summary["already_linked"] += 1
            continue

        year = media.release_date.year if media.release_date else None
        candidates = await tmdb.search(media.title, is_series=is_series(media.type), year=year)
        match = select_confident_match(media, candidates)
        if not match:
            reason = "not_found" if not candidates else "ambiguous"
            report_rows.append({
                "media_id": media.id,
                "title": media.title,
                "type": media.type or "",
                "year": str(year or ""),
                "reason": reason,
                "candidates": _candidate_text(candidates),
            })
            summary["to_review"] += 1
            continue

        tmdb_id = int(match["id"])
        if apply:
            details = await tmdb.get_details(tmdb_id, is_series=is_series(media.type))
            if not details:
                report_rows.append({
                    "media_id": media.id,
                    "title": media.title,
                    "type": media.type or "",
                    "year": str(year or ""),
                    "reason": "details_unavailable",
                    "candidates": _candidate_text(candidates),
                })
                summary["to_review"] += 1
                continue
            await store.update(media.id, build_relink_updates(media, details, tmdb, tmdb_id))
        summary["linked"] += 1

    _write_report(report_path, report_rows)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Réassocie prudemment les fiches Backstage à TMDB.")
    parser.add_argument("--apply", action="store_true", help="Écrit les associations sûres dans SQLite.")
    parser.add_argument("--report", type=Path, default=Path("tmdb-a-verifier.csv"), help="Chemin du rapport CSV.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    store = MediaStore(Config.DB_PATH)
    store.init_schema()
    summary = await relink_missing_tmdb_ids(store, TMDBClient(), apply=args.apply, report_path=args.report)
    mode = "appliquées" if args.apply else "prévisualisées"
    print(
        f"Associations sûres {mode} : {summary['linked']}; "
        f"à vérifier : {summary['to_review']}; déjà reliées : {summary['already_linked']}."
    )
    print(f"Rapport : {args.report.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
