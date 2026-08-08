import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    DB_PATH = os.getenv("DB_PATH", "backstage.db")
    PORT = int(os.getenv("PORT", "8090"))
    RECOMMENDATION_DAILY_LIMIT = int(os.getenv("RECOMMENDATION_DAILY_LIMIT", "2") or "2")
    RECOMMENDATION_TIMEZONE = os.getenv("RECOMMENDATION_TIMEZONE", "Europe/Paris")
    RECOMMENDATION_RECENT_DAYS = int(os.getenv("RECOMMENDATION_RECENT_DAYS", "30") or "30")
    AUTH_RATE_LIMIT_WINDOW_SEC = int(os.getenv("AUTH_RATE_LIMIT_WINDOW_SEC", "300") or "300")
    AUTH_RATE_LIMIT_MAX_ATTEMPTS = int(os.getenv("AUTH_RATE_LIMIT_MAX_ATTEMPTS", "5") or "5")
    AUTH_RATE_LIMIT_BLOCK_SEC = int(os.getenv("AUTH_RATE_LIMIT_BLOCK_SEC", "900") or "900")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "256") or "256")

    RADARR_URL = os.getenv("RADARR_URL", "http://127.0.0.1:7878")
    RADARR_API_KEY = os.getenv("RADARR_API_KEY")
    RADARR_DEFAULT_QUALITY_PROFILE_NAME = os.getenv("RADARR_DEFAULT_QUALITY_PROFILE_NAME", "1080p FR - max 10 Go")
    RADARR_DEFAULT_ROOT_FOLDER = os.getenv("RADARR_DEFAULT_ROOT_FOLDER") or None
    SONARR_URL = os.getenv("SONARR_URL", "http://127.0.0.1:8989")
    SONARR_API_KEY = os.getenv("SONARR_API_KEY")
    SEERR_URL = os.getenv("SEERR_URL", "http://127.0.0.1:5055")
    SEERR_API_KEY = os.getenv("SEERR_API_KEY")
    JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://127.0.0.1:8096")
    JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY")
    JELLYFIN_SERVER_ID = os.getenv("JELLYFIN_SERVER_ID")
    MEDIA_SYNC_INTERVAL_SEC = int(os.getenv("MEDIA_SYNC_INTERVAL_SEC", "60") or "60")
    MIN_FREE_GB = float(os.getenv("MIN_FREE_GB", "20") or "20")
    TEMPORARY_MAX_GB = float(os.getenv("TEMPORARY_MAX_GB", "500") or "500")
    BACKUP_DIR = os.getenv("BACKUP_DIR", "/data/backups")
    BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "7") or "7")
    BACKUP_INTERVAL_HOURS = float(os.getenv("BACKUP_INTERVAL_HOURS", "24") or "24")
    BACKUP_MAX_AGE_HOURS = float(os.getenv("BACKUP_MAX_AGE_HOURS", "30") or "30")
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

    @classmethod
    def min_free_bytes(cls) -> int:
        return int(cls.MIN_FREE_GB * 1024**3)

    @classmethod
    def temporary_max_bytes(cls) -> int:
        return int(cls.TEMPORARY_MAX_GB * 1024**3)
