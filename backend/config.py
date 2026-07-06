import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Conservés pour le script de migration one-shot (scripts/migrate_from_notion.py)
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    DATABASE_ID = os.getenv("DATABASE_ID")

    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    DB_PATH = os.getenv("DB_PATH", "backstage.db")

    # Optionnels (fonctionnalités avancées, dégradation propre si absents)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OMDB_API_KEY = os.getenv("OMDB_API_KEY")
    # Intervalle de sync auto en minutes (0 = désactivé)
    SYNC_INTERVAL_MIN = int(os.getenv("SYNC_INTERVAL_MIN", "0") or "0")

    @classmethod
    def ai_enabled(cls) -> bool:
        return bool(cls.ANTHROPIC_API_KEY)

    @classmethod
    def omdb_enabled(cls) -> bool:
        return bool(cls.OMDB_API_KEY)
