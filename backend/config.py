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
    SEERR_URL = os.getenv("SEERR_URL", "http://127.0.0.1:5055")
    SEERR_API_KEY = os.getenv("SEERR_API_KEY")
    JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096")
    JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY")
    JELLYFIN_SERVER_ID = os.getenv("JELLYFIN_SERVER_ID")
    MEDIA_SYNC_INTERVAL_SEC = int(os.getenv("MEDIA_SYNC_INTERVAL_SEC", "60") or "60")
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_FROM = os.getenv("SMTP_FROM")
    BACKSTAGE_PUBLIC_URL = os.getenv("BACKSTAGE_PUBLIC_URL", "http://localhost:8090")

    @classmethod
    def radarr_enabled(cls) -> bool:
        return bool(cls.RADARR_API_KEY)

    @classmethod
    def sonarr_enabled(cls) -> bool:
        return bool(cls.SONARR_API_KEY)

    @classmethod
    def seerr_enabled(cls) -> bool:
        return bool(cls.SEERR_API_KEY)

    @classmethod
    def jellyfin_enabled(cls) -> bool:
        return bool(cls.JELLYFIN_API_KEY)

    @classmethod
    def media_server_enabled(cls) -> bool:
        return cls.radarr_enabled() or cls.sonarr_enabled() or cls.seerr_enabled()
