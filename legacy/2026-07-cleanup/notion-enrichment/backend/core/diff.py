"""Traduction d'un dict de mise à jour (valeurs Media simples) en diff lisible (mode dry-run)."""
from typing import Dict, Any, List, Optional

from backend.core.mapping import FIELD_LABELS
from backend.core.models import Media


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


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
    for field, value in updates.items():
        new = _format_value(value)
        old = _format_value(getattr(media, field, None))
        if new and new != old:
            changes.append({"field": FIELD_LABELS.get(field, field), "old": old or "—", "new": new})

    if poster_url and not media.cover_url:
        changes.append({"field": "Couverture", "old": "—", "new": "Affiche TMDB"})

    return changes
