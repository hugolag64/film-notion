"""Agrégats pour le dashboard de statistiques + détection de doublons."""
from collections import Counter
from typing import List, Dict, Any
import unicodedata

from backend.core.models import Media


def _norm(title: str) -> str:
    """Normalise un titre pour comparer (casse, accents, espaces)."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.lower().split())


def compute_stats(medias: List[Media]) -> Dict[str, Any]:
    """Statistiques globales de la collection."""
    total = len(medias)
    enriched = sum(1 for m in medias if m.tmdb_ok)
    rated = sum(1 for m in medias if m.rating)
    without_director = sum(1 for m in medias if not m.director)

    genres = Counter(g for m in medias for g in m.categories)
    by_support = Counter(m.support or "Inconnu" for m in medias)
    by_status = Counter(m.status or "Inconnu" for m in medias)

    return {
        "total": total,
        "enriched": enriched,
        "enriched_pct": round(100 * enriched / total) if total else 0,
        "rated": rated,
        "without_director": without_director,
        "top_genres": genres.most_common(8),
        "by_support": by_support.most_common(),
        "by_status": by_status.most_common(),
    }


def find_duplicates(medias: List[Media]) -> List[Dict[str, Any]]:
    """Groupes de fiches partageant le même titre normalisé (2+ occurrences)."""
    groups: Dict[str, List[Media]] = {}
    for m in medias:
        groups.setdefault(_norm(m.title), []).append(m)

    duplicates = []
    for key, items in groups.items():
        if len(items) > 1:
            duplicates.append({
                "title": items[0].title,
                "count": len(items),
                "ids": [m.id for m in items],
            })
    return sorted(duplicates, key=lambda d: -d["count"])
