"""Journal d'audit append-only des enrichissements appliqués (history.jsonl)."""
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

HISTORY_FILE = "history.jsonl"


def record(page_id: str, title: str, changes: List[Dict[str, str]], source: str = "auto"):
    """Ajoute une entrée d'historique (une ligne JSON)."""
    if not changes:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "page_id": page_id,
        "title": title,
        "source": source,  # auto | manual
        "fields": [c["field"] for c in changes],
        "changes": changes,
    }
    try:
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error("Erreur écriture historique: %s", e)


def read_recent(limit: int = 50) -> List[Dict[str, Any]]:
    """Lit les dernières entrées (plus récentes en premier)."""
    import os
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = [json.loads(line) for line in lines if line.strip()]
        return list(reversed(entries))[:limit]
    except Exception as e:
        logger.error("Erreur lecture historique: %s", e)
        return []
