import os
import sys
from dotenv import load_dotenv
from notion_client import Client

# =====================
# CONFIGURATION
# =====================

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

# Racines
NAS_ROOT_LOCAL = r"H:\Movies"               # PC Windows (scan)
NAS_ROOT_LINUX = "/share/Multimedia/Movies" # NAS Linux (info only)
NAS_HOST = "naslag"                         # SMB (info only)

if not NOTION_TOKEN or not DATABASE_ID:
    print("❌ NOTION_TOKEN ou DATABASE_ID manquant")
    sys.exit(1)

notion = Client(auth=NOTION_TOKEN)

# =====================
# IMPORTS SCAN NAS
# =====================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.nas_scanner import (
    scan_nas_movies,
    normalize_title,
    extract_year
)

# =====================
# NOTION FETCH
# =====================

def fetch_notion_films():
    results = []
    cursor = None

    while True:
        response = notion.databases.query(
            database_id=DATABASE_ID,
            start_cursor=cursor
        )
        results.extend(response["results"])
        cursor = response.get("next_cursor")
        if not cursor:
            break

    return results

# =====================
# MATCHING
# =====================

def find_match(notion_title, nas_movies):
    norm_title = normalize_title(notion_title)
    year = extract_year(notion_title)

    for movie in nas_movies:
        if norm_title in movie["normalized"]:
            if not year or year == movie["year"]:
                return movie

    return None

# =====================
# PATH BUILDERS (INFO ONLY)
# =====================

def build_paths(local_path: str):
    """
    Construit des chemins à titre informatif (logs uniquement)
    """
    relative = os.path.relpath(local_path, NAS_ROOT_LOCAL)
    relative = relative.replace("\\", "/")

    linux_path = f"{NAS_ROOT_LINUX}/{relative}"
    smb_url = f"file://{NAS_HOST}/Multimedia/Movies/{relative}"

    return linux_path, smb_url

# =====================
# SYNC CORE (READ-ONLY)
# =====================

def sync_nas_to_notion():
    print("🔍 Scan du NAS local...")
    nas_movies = scan_nas_movies(NAS_ROOT_LOCAL)
    print(f"🎞️ {len(nas_movies)} fichiers trouvés")

    print("📡 Chargement des films Notion...")
    notion_films = fetch_notion_films()
    print(f"📄 {len(notion_films)} pages Notion")

    found = 0
    missing = 0

    for film in notion_films:
        props = film["properties"]
        title_prop = props.get("Nom", {}).get("title", [])

        if not title_prop:
            continue

        title = title_prop[0]["plain_text"]

        match = find_match(title, nas_movies)

        if not match:
            print(f"❌ {title} absent du NAS")
            missing += 1
            continue

        local_path = match["path"]
        linux_path, smb_url = build_paths(local_path)

        print(f"✅ {title}")
        print(f"   NAS → {linux_path}")
        print(f"   SMB → {smb_url}")

        found += 1

    print("\n=====================")
    print(f"🎬 Films trouvés sur le NAS : {found}")
    print(f"📭 Films absents du NAS     : {missing}")
    print("✅ Sync NAS → Notion terminée (lecture seule)")

# =====================
# CLI ENTRY POINT
# =====================

if __name__ == "__main__":
    sync_nas_to_notion()
