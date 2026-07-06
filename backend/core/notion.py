import logging
import httpx
from backend.config import Config
from backend.core.models import Media
from backend.core import http
from typing import List, Optional, Any, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class Props:
    """Noms exacts des propriétés Notion (utilisé uniquement par ce module,
    conservé pour le script de migration one-shot)."""
    TITLE = "Nom"
    TYPE = "Type"
    STATUS = "Statut"
    SUPPORT = "Support"
    RATING = "Note /10"
    RELEASE_DATE = "Date de sortie"
    DIRECTOR = "Réalisateur"
    CATEGORY = "Catégorie"
    SYNOPSIS = "Synopsis"
    TAGS = "Tags"
    REVIEW = "Avis"
    TMDB_OK = "TMDB_OK"


class NotionService:
    # On utilise httpx directement pour contourner les problèmes de la lib notion interactifs
    BASE_URL = "https://api.notion.com/v1"

    @classmethod
    def _headers(cls) -> Dict[str, str]:
        """Construit les en-têtes à l'appel (token lu au runtime, pas à l'import)."""
        return {
            "Authorization": f"Bearer {Config.NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_property(page: Dict[str, Any], prop_name: str) -> Any:
        props = page.get("properties", {})
        prop = props.get(prop_name)

        if not prop:
            return None

        actual_type = prop.get("type")
        content = prop.get(actual_type)
        if content is None:
            return None

        if actual_type == "title":
            return content[0]["plain_text"] if content else ""
        elif actual_type == "rich_text":
            return content[0]["plain_text"] if content else ""
        elif actual_type == "select":
            return content["name"] if content else None
        elif actual_type == "multi_select":
            return [item["name"] for item in content]
        elif actual_type == "date":
            date_str = content.get("start")
            if date_str:
                try:
                    return datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    return None
            return None
        elif actual_type in ("checkbox", "url", "number"):
            return content

        return None

    @classmethod
    async def fetch_all_media(cls) -> List[Media]:
        medias = []
        has_more = True
        next_cursor = None
        page_count = 0
        MAX_PAGES = 50

        logger.info("Récupération de la base Notion %s...", Config.DATABASE_ID)

        url = f"{cls.BASE_URL}/databases/{Config.DATABASE_ID}/query"
        while has_more and page_count < MAX_PAGES:
            page_count += 1
            try:
                body = {"page_size": 100}
                if next_cursor:
                    body["start_cursor"] = next_cursor

                response = await http.request_with_retry("POST", url, headers=cls._headers(), json=body)

                if response.status_code != 200:
                    logger.error("Erreur Notion %s: %s", response.status_code, response.text)
                    break

                data = response.json()
                results = data.get("results", [])
                logger.debug("Page %s : %s éléments.", page_count, len(results))

                if not results:
                    break

                for page in results:
                    media_obj = cls._map_page_to_media(page)
                    if media_obj:
                        medias.append(media_obj)

                has_more = data.get("has_more", False)
                next_cursor = data.get("next_cursor")

            except Exception as e:
                logger.exception("Erreur récupération Notion: %s", e)
                break

        logger.info("Total récupéré : %s films.", len(medias))
        return medias

    @classmethod
    async def fetch_page(cls, page_id: str) -> Optional[Media]:
        """Récupère une seule fiche Notion par son ID."""
        url = f"{cls.BASE_URL}/pages/{page_id}"
        try:
            response = await http.request_with_retry("GET", url, headers=cls._headers())
            if response.status_code != 200:
                logger.error("Erreur fetch page %s: %s", page_id, response.text)
                return None
            return cls._map_page_to_media(response.json())
        except Exception as e:
            logger.exception("Exception fetch page %s: %s", page_id, e)
            return None

    @classmethod
    async def update_page(cls, page_id: str, properties: Dict[str, Any], cover_url: Optional[str] = None):
        url = f"{cls.BASE_URL}/pages/{page_id}"

        payload = {"properties": properties}
        if cover_url:
            payload["cover"] = {"type": "external", "external": {"url": cover_url}}

        try:
            response = await http.request_with_retry("PATCH", url, headers=cls._headers(), json=payload)
            if response.status_code != 200:
                logger.error("Erreur update page %s: %s", page_id, response.text)
                return False
            return True
        except Exception as e:
            logger.exception("Exception update page %s: %s", page_id, e)
            return False

    @classmethod
    async def append_image_block(cls, page_id: str, image_url: str):
        url = f"{cls.BASE_URL}/blocks/{page_id}/children"
        payload = {
            "children": [
                {
                    "object": "block",
                    "type": "image",
                    "image": {"type": "external", "external": {"url": image_url}},
                }
            ]
        }
        try:
            response = await http.request_with_retry("PATCH", url, headers=cls._headers(), json=payload)
            if response.status_code != 200:
                logger.error("Erreur ajout bloc image page %s: %s", page_id, response.text)
                return False
            return True
        except Exception as e:
            logger.exception("Exception ajout bloc image page %s: %s", page_id, e)
            return False

    @classmethod
    def _map_page_to_media(cls, page: Dict[str, Any]) -> Optional[Media]:
        try:
            cover = page.get("cover") or {}
            cover_url = cover.get("external", {}).get("url") if cover.get("type") == "external" else None
            return Media(
                id=page["id"],
                title=cls._extract_property(page, Props.TITLE) or "Sans titre",
                type=cls._extract_property(page, Props.TYPE),
                status=cls._extract_property(page, Props.STATUS),
                support=cls._extract_property(page, Props.SUPPORT),
                rating=cls._extract_property(page, Props.RATING),
                release_date=cls._extract_property(page, Props.RELEASE_DATE),
                director=cls._extract_property(page, Props.DIRECTOR),
                categories=cls._extract_property(page, Props.CATEGORY) or [],
                synopsis=cls._extract_property(page, Props.SYNOPSIS),
                tags=cls._extract_property(page, Props.TAGS) or [],
                review=cls._extract_property(page, Props.REVIEW),
                tmdb_ok=cls._extract_property(page, Props.TMDB_OK) or False,
                cover_url=cover_url,
            )
        except Exception as e:
            logger.error("Erreur mapping page %s: %s", page.get("id"), e)
            return None
