import os
import logging

from nicegui import ui, app

from backend.config import Config
from backend.core import http, scheduler
from backend.core.notion import NotionService
import frontend.ui  # noqa: F401  (enregistre la page via @ui.page)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Échoue tôt et clairement si une variable d'environnement manque
Config.check()

# Validation du schéma Notion au démarrage (fail fast, avertit si non bloquant)
try:
    problems = NotionService.validate_schema_sync()
    if problems:
        for p in problems:
            logger.warning("Schéma Notion : %s", p)
        logger.warning("L'enrichissement peut échouer sur les propriétés ci-dessus.")
    else:
        logger.info("Schéma Notion conforme.")
except Exception as e:
    logger.error("Impossible de valider le schéma Notion : %s", e)

# Synchronisation auto périodique (si SYNC_INTERVAL_MIN > 0)
app.on_startup(scheduler.start)

# Ferme proprement le client HTTP partagé à l'arrêt
app.on_shutdown(http.aclose)

# reload=True uniquement en dev (BACKSTAGE_DEV=1)
RELOAD = os.getenv("BACKSTAGE_DEV", "0") == "1"

ui.run(title="Backstage - Vidéothèque", port=8080, reload=RELOAD)
