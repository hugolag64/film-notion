import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    NOTION_TOKEN = os.getenv("NOTION_TOKEN")
    DATABASE_ID = os.getenv("DATABASE_ID")
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    # Optionnels (fonctionnalités avancées, dégradation propre si absents)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OMDB_API_KEY = os.getenv("OMDB_API_KEY")
    # Intervalle de sync auto en minutes (0 = désactivé)
    SYNC_INTERVAL_MIN = int(os.getenv("SYNC_INTERVAL_MIN", "0") or "0")

    @classmethod
    def check(cls):
        missing = []
        if not cls.NOTION_TOKEN: missing.append("NOTION_TOKEN")
        if not cls.DATABASE_ID: missing.append("DATABASE_ID")
        # TMDB pas encore obligatoire pour la phase 1, mais bon de l'avoir
        # if not cls.TMDB_API_KEY: missing.append("TMDB_API_KEY")

        if missing:
            raise ValueError(f"Variables d'environnement manquantes : {', '.join(missing)}")

    @classmethod
    def ai_enabled(cls) -> bool:
        return bool(cls.ANTHROPIC_API_KEY)

    @classmethod
    def omdb_enabled(cls) -> bool:
        return bool(cls.OMDB_API_KEY)
