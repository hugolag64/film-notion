import os
import platform
import subprocess
from fastapi import FastAPI, HTTPException
from notion_client import Client
from dotenv import load_dotenv

# =====================
# ENV
# =====================

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")

if not NOTION_TOKEN or not DATABASE_ID:
    raise RuntimeError("NOTION_TOKEN ou DATABASE_ID manquant")

notion = Client(auth=NOTION_TOKEN)
app = FastAPI(title="Film NAS Server")

# =====================
# UTILS
# =====================

def get_nas_path(movie_id: str) -> str | None:
    """Récupère le NAS Path depuis Notion"""
    page = notion.pages.retrieve(page_id=movie_id)
    props = page["properties"]

    nas_prop = props.get("NAS Path")
    if not nas_prop or nas_prop["type"] != "rich_text":
        return None

    rich = nas_prop["rich_text"]
    if not rich:
        return None

    return rich[0]["plain_text"]


def open_file(path: str):
    """Ouvre le fichier selon l'OS"""
    system = platform.system()

    if system == "Windows":
        os.startfile(path)
    elif system == "Linux":
        subprocess.Popen(["xdg-open", path])
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        raise RuntimeError(f"Système non supporté : {system}")

# =====================
# ROUTES
# =====================

@app.get("/health")
def health():
    return {"status": "ok"}

# 🔧 Ancienne route (compat)
@app.get("/open")
def open_movie(movie_id: str):
    return _open_movie(movie_id)

# ✨ Route principale (utilisée par Notion)
@app.get("/play/{movie_id}")
def play_movie(movie_id: str):
    return _open_movie(movie_id)

# =====================
# CORE LOGIC
# =====================

def _open_movie(movie_id: str):
    path = get_nas_path(movie_id)

    if not path:
        raise HTTPException(
            status_code=404,
            detail="Aucun NAS Path trouvé pour ce film"
        )

    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"Fichier introuvable sur le NAS : {path}"
        )

    open_file(path)
    return {
        "status": "ok",
        "path": path
    }
