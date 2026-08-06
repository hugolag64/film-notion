import os
import logging

from nicegui import ui, app
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import Config
from backend.core import http, scheduler
from backend.core.store import MediaStore
from backend.core.auth import AuthStore
from backend.api import health_router, router as api_router
from backend.auth_api import auth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Inclure les routes de santé et de l'API REST
app.include_router(health_router)
app.include_router(api_router)
app.include_router(auth_router)

LOGO_PATH = os.path.join(os.path.dirname(__file__), "Logo.png")


@app.get("/static/Logo.png", include_in_schema=False)
def serve_logo():
    return FileResponse(LOGO_PATH)

# Servir le nouveau Frontend React (proto-ui/dist) sur la racine
DIST_DIR = os.path.join(os.path.dirname(__file__), "proto-ui", "dist")
if os.path.exists(DIST_DIR):
    assets_dir = os.path.join(DIST_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="react_assets")

    @ui.page("/")
    def serve_index():
        return FileResponse(os.path.join(DIST_DIR, "index.html"))
else:
    raise RuntimeError("Le frontend React compilé (proto-ui/dist) est requis.")

# Crée la base locale si elle n'existe pas encore
MediaStore(Config.DB_PATH).init_schema()
AuthStore(Config.DB_PATH).init_schema()

# Synchronisation auto périodique (si SYNC_INTERVAL_MIN > 0)
app.on_startup(scheduler.start_media_server_sync)

# Ferme proprement le client HTTP partagé à l'arrêt
app.on_shutdown(http.aclose)


# reload=True uniquement en dev (BACKSTAGE_DEV=1)
RELOAD = os.getenv("BACKSTAGE_DEV", "0") == "1"

ui.run(title="Backstage - Vidéothèque", port=Config.PORT, reload=RELOAD)
