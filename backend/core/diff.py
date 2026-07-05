"""Traduction d'un payload de mise à jour Notion en diff lisible (mode dry-run)."""
from typing import Dict, Any, List, Optional

from backend.core.models import Media


def _decode_value(prop: Dict[str, Any]) -> str:
    """Rend une valeur de propriété Notion sous forme de texte lisible."""
    if "select" in prop:
        return prop["select"].get("name", "")
    if "multi_select" in prop:
        return ", ".join(item.get("name", "") for item in prop["multi_select"])
    if "rich_text" in prop:
        return "".join(t.get("text", {}).get("content", "") for t in prop["rich_text"])
    if "date" in prop:
        return prop["date"].get("start", "")
    if "checkbox" in prop:
        return "Oui" if prop["checkbox"] else "Non"
    return str(prop)


def _current_value(media: Media, field: str) -> str:
    mapping = {
        "Statut": media.status,
        "Support": media.support,
        "Réalisateur": media.director,
        "Synopsis": media.synopsis,
        "Date de sortie": str(media.release_date) if media.release_date else "",
        "Catégorie": ", ".join(media.categories),
        "Tags": ", ".join(media.tags),
        "TMDB_OK": "Oui" if media.tmdb_ok else "Non",
    }
    return mapping.get(field) or ""


def summarize_changes(
    media: Media,
    updates: Dict[str, Any],
    poster_url: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Retourne la liste des changements prévus : [{'field', 'old', 'new'}, ...].
    Inclut la couverture si une affiche va être posée.
    """
    changes: List[Dict[str, str]] = []
    for field, prop in updates.items():
        new = _decode_value(prop)
        old = _current_value(media, field)
        if new and new != old:
            changes.append({"field": field, "old": old or "—", "new": new})

    if poster_url and not media.cover_url:
        changes.append({"field": "Couverture", "old": "—", "new": "Affiche TMDB"})

    return changes
