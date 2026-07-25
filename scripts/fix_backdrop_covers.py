"""
Backfill ponctuel : remplace les cover_url historiques pointant vers une image
"backdrop" TMDB (paysage, t/p/w780/...) par la vraie affiche (portrait, w500),
en recherchant chaque film concerné sur TMDB par titre/année.

Ces URLs erronées viennent d'un import Notion antérieur (la couverture de page
Notion, pensée pour un bandeau paysage, avait été réutilisée comme cover_url).
Le code actuel ne génère plus jamais ce format, donc ce script ne s'exécute
qu'une fois pour assainir les données existantes.

Usage : python scripts/fix_backdrop_covers.py [--dry-run]
"""
import asyncio
import sys

from backend.config import Config
from backend.core.mapping import is_series
from backend.core.processor import EnrichmentProcessor
from backend.core.store import MediaStore

LEGACY_BACKDROP_MARKER = "/t/p/w780/"


async def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    dry_run = "--dry-run" in sys.argv

    store = MediaStore(Config.DB_PATH)
    processor = EnrichmentProcessor(store)

    medias = await store.fetch_all()
    affected = [m for m in medias if m.cover_url and LEGACY_BACKDROP_MARKER in m.cover_url]

    print(f"{len(affected)} fiche(s) avec une affiche 'backdrop' héritée sur {len(medias)} au total.")
    if dry_run:
        print("(dry-run : aucune écriture ne sera faite)")

    fixed, not_found, no_poster = 0, 0, 0

    for media in affected:
        series = is_series(media.type)
        year = media.release_date.year if media.release_date else None

        results = await processor.tmdb.search(media.title, is_series=series, year=year)
        best = processor._find_best_match(media, results)

        if not best:
            not_found += 1
            print(f"  [MISS] Aucun match TMDB : {media.title!r}")
            continue

        details = await processor.tmdb.get_details(best["id"], is_series=series)
        poster_url = processor.tmdb.get_poster_url(details) if details else None

        if not poster_url:
            no_poster += 1
            print(f"  [MISS] Pas d'affiche TMDB disponible : {media.title!r}")
            continue

        if not dry_run:
            await store.update(media.id, {"cover_url": poster_url})
        fixed += 1
        print(f"  [OK] {media.title!r} -> {poster_url}")

    print(f"\nRésumé : {fixed} corrigée(s), {not_found} sans match, {no_poster} sans affiche.")


if __name__ == "__main__":
    asyncio.run(main())
