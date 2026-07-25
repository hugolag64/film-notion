import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    DB_PATH = os.getenv("DB_PATH", "backstage.db")
    PORT = int(os.getenv("PORT", "8090"))

    RADARR_URL = os.getenv("RADARR_URL", "http://127.0.0.1:7878")
    RADARR_API_KEY = os.getenv("RADARR_API_KEY")
    SONARR_URL = os.getenv("SONARR_URL", "http://127.0.0.1:8989")
    SONARR_API_KEY = os.getenv("SONARR_API_KEY")
    JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096")
    JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY")
    MEDIA_SYNC_INTERVAL_SEC = int(os.getenv("MEDIA_SYNC_INTERVAL_SEC", "60") or "60")

    @classmethod
    def radarr_enabled(cls) -> bool:
        return bool(cls.RADARR_API_KEY)

    @classmethod
    def sonarr_enabled(cls) -> bool:
        return bool(cls.SONARR_API_KEY)

    @classmethod
    def jellyfin_enabled(cls) -> bool:
        return bool(cls.JELLYFIN_API_KEY)

    @classmethod
    def media_server_enabled(cls) -> bool:
        return cls.radarr_enabled() or cls.sonarr_enabled()
