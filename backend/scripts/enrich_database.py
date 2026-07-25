"""Script to mass enrich movies in SQLite database with real TMDB posters, 16:9 backdrops, and cast."""
import asyncio
import logging
from backend.config import Config
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("enrich_script")


async def enrich_all_db_medias():
    store = MediaStore(Config.DB_PATH)
    tmdb = TMDBClient()
    medias = await store.fetch_all()

    logger.info(f"Début de l'enrichissement TMDB pour {len(medias)} médias...")

    updated_count = 0
    for media in medias:
        try:
            # Recherche TMDB
            results = await tmdb.search_movie(media.title)
            if not results:
                continue

            best_match = results[0]
            tmdb_id = best_match["id"]
            details = await tmdb.get_movie_details(tmdb_id)
            if not details:
                continue

            updates = {}

            # Cover / Poster URL
            poster_url = tmdb.get_poster_url(details)
            if poster_url:
                updates["cover_url"] = poster_url

            # Backdrop 16:9 Horizontal URL
            backdrop_url = tmdb.get_backdrop_url(details)
            if backdrop_url:
                updates["backdrop_url"] = backdrop_url

            # Cast (Acteurs principaux)
            cast = tmdb.get_cast(details, limit=5)
            if cast:
                updates["cast"] = cast

            # Director / Synopsis / Categories if missing
            director = tmdb.get_director(details)
            if director and not media.director:
                updates["director"] = director

            synopsis = details.get("overview")
            if synopsis and not media.synopsis:
                updates["synopsis"] = synopsis[:2000]

            genres = tmdb.get_genres(details)
            if genres and not media.categories:
                updates["categories"] = genres

            if updates:
                updates["tmdb_ok"] = True
                await store.update(media.id, updates)
                updated_count += 1
                logger.info(f"Mise à jour réussie pour '{media.title}': cast={cast[:2]}, poster={'OK' if poster_url else 'NO'}, backdrop={'OK' if backdrop_url else 'NO'}")

        except Exception as e:
            logger.error(f"Erreur lors de l'enrichissement de '{media.title}': {e}")

    logger.info(f"Fin de l'enrichissement TMDB. Total mis à jour : {updated_count} / {len(medias)}")


if __name__ == "__main__":
    asyncio.run(enrich_all_db_medias())
