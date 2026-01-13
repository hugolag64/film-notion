import os
from dotenv import load_dotenv
from notion_client import Client
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==================================================
# Chargement ENV
# ==================================================

load_dotenv()

# ==================================================
# Variables d'environnement
# ==================================================

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# ==================================================
# Sécurités minimales (fail fast)
# ==================================================

missing = [
    name for name, value in {
        "NOTION_TOKEN": NOTION_TOKEN,
        "DATABASE_ID": DATABASE_ID,
        "TMDB_API_KEY": TMDB_API_KEY,
        "GOOGLE_CALENDAR_CREDENTIALS": SERVICE_ACCOUNT_FILE,
        "GOOGLE_CALENDAR_ID": CALENDAR_ID,
    }.items()
    if not value
]

if missing:
    raise RuntimeError(
        "❌ Variables d'environnement manquantes :\n"
        + "\n".join(f"- {m}" for m in missing)
    )

# ==================================================
# Clients API
# ==================================================

# --- Notion ---
notion = Client(auth=NOTION_TOKEN)

# --- Google Calendar ---
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)

calendar_service = build(
    "calendar",
    "v3",
    credentials=credentials,
    cache_discovery=False  # évite warnings & bugs cache
)
