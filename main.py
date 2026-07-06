import os
import logging

from nicegui import ui, app

from backend.config import Config
from backend.core import http, scheduler
from backend.core.store import MediaStore
import frontend.ui  # noqa: F401  (enregistre la page via @ui.page)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Crée la base locale si elle n'existe pas encore
MediaStore(Config.DB_PATH).init_schema()

# Synchronisation auto périodique (si SYNC_INTERVAL_MIN > 0)
app.on_startup(scheduler.start)

# Ferme proprement le client HTTP partagé à l'arrêt
app.on_shutdown(http.aclose)

# reload=True uniquement en dev (BACKSTAGE_DEV=1)
RELOAD = os.getenv("BACKSTAGE_DEV", "0") == "1"

ui.run(title="Backstage - Vidéothèque", port=8080, reload=RELOAD)
