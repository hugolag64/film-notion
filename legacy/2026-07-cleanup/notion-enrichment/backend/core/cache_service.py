import json
import os
import hashlib
import logging
from typing import Dict, Any
from backend.core.models import Media

logger = logging.getLogger(__name__)


class CacheService:
    CACHE_FILE = "cache.json"

    def __init__(self):
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_cache(self):
        try:
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Erreur sauvegarde cache: %s", e)

    @staticmethod
    def _content_hash(media: Media) -> str:
        """Empreinte des champs significatifs : si la fiche Notion change, le hash change."""
        payload = "|".join([
            media.title or "",
            media.status or "",
            media.support or "",
            media.director or "",
            str(media.release_date or ""),
            media.synopsis or "",
            ",".join(sorted(media.categories)),
            ",".join(sorted(media.tags)),
            str(media.tmdb_ok),
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_processed(self, media: Media) -> bool:
        """Vrai seulement si la fiche a été traitée ET n'a pas changé depuis."""
        entry = self.cache.get(media.id)
        if not entry or not entry.get("processed"):
            return False
        return entry.get("hash") == self._content_hash(media)

    def mark_as_processed(self, media: Media):
        """Marque une fiche comme traitée et mémorise l'empreinte de son contenu."""
        self.cache[media.id] = {
            "processed": True,
            "title": media.title,
            "hash": self._content_hash(media),
        }
        self.save_cache()

    def invalidate(self, page_id: str):
        """Force le re-traitement d'une fiche au prochain passage."""
        if page_id in self.cache:
            del self.cache[page_id]
            self.save_cache()

    def clear(self):
        """Vide tout le cache (re-traitement complet)."""
        self.cache = {}
        self.save_cache()
