"""
Migration one-shot : importe tous les films de la base Notion existante dans
la base locale SQLite, en conservant les IDs Notion d'origine (pour que
cache.json, indexé par id, reste valide après la bascule).

Usage : python scripts/migrate_from_notion.py
Nécessite NOTION_TOKEN et DATABASE_ID dans l'environnement (.env).
"""
import asyncio
import logging

from backend.config import Config
from backend.core.notion import NotionService
from backend.core.store import MediaStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    if not Config.NOTION_TOKEN or not Config.DATABASE_ID:
        raise SystemExit("NOTION_TOKEN et DATABASE_ID doivent être définis pour la migration.")

    store = MediaStore(Config.DB_PATH)
    store.init_schema()

    medias = await NotionService.fetch_all_media()
    logger.info("Récupéré %s films depuis Notion, import en cours...", len(medias))

    for media in medias:
        await store.create(media.model_dump())

    logger.info("Migration terminée : %s films importés dans %s.", len(medias), Config.DB_PATH)


if __name__ == "__main__":
    asyncio.run(main())
