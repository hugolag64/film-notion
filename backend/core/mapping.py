"""Règles métier partagées (statuts, genres, libellés d'affichage)."""
from typing import Dict


class Values:
    """Valeurs de statut/support appliquées par les règles métier."""
    STATUS_TO_WATCH = "À regarder"
    SUPPORT_CINEMA = "Cinéma"
    SUPPORT_DOWNLOAD = "À télécharger"


# Valeurs de la propriété "type" interprétées comme des séries TV (sinon : film)
SERIES_TYPES = {"Série", "Serie", "Séries", "TV", "Série TV"}


def is_series(media_type) -> bool:
    return bool(media_type) and media_type in SERIES_TYPES


# Règles genre TMDB (fr-FR) -> tag
GENRE_TAG_RULES: Dict[str, str] = {
    "Comédie": "😌 Détente",
    "Animation": "👨‍👩‍👧‍👦 Familial",
    "Familial": "👨‍👩‍👧‍👦 Familial",
    "Horreur": "⚠️ Film dur",
    "Documentaire": "🧠 Complexe",
    "Histoire": "🎬 Classique",
    "Drame": "😢 Triste",
}

# Libellés français affichés dans l'aperçu dry-run (nom de champ Media -> libellé)
FIELD_LABELS: Dict[str, str] = {
    "status": "Statut",
    "support": "Support",
    "director": "Réalisateur",
    "synopsis": "Synopsis",
    "release_date": "Date de sortie",
    "categories": "Catégorie",
    "tags": "Tags",
    "tmdb_ok": "TMDB_OK",
    "cover_url": "Couverture",
}
