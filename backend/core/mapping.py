"""
Couplage centralisé au schéma Notion.

Tout ce qui dépend des noms/valeurs de la base Notion vit ici, pour qu'un
renommage côté Notion se corrige à un seul endroit (et soit validé au démarrage).
"""
from typing import Dict


class Props:
    """Noms exacts des propriétés Notion."""
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


class Values:
    """Valeurs de select appliquées par les règles métier."""
    STATUS_TO_WATCH = "À regarder"
    SUPPORT_CINEMA = "Cinéma"
    SUPPORT_DOWNLOAD = "À télécharger"


# Valeurs de la propriété "Type" interprétées comme des séries TV (sinon : film)
SERIES_TYPES = {"Série", "Serie", "Séries", "TV", "Série TV"}


def is_series(media_type) -> bool:
    return bool(media_type) and media_type in SERIES_TYPES


# Règles genre TMDB (fr-FR) -> tag Notion
GENRE_TAG_RULES: Dict[str, str] = {
    "Comédie": "😌 Détente",
    "Animation": "👨‍👩‍👧‍👦 Familial",
    "Familial": "👨‍👩‍👧‍👦 Familial",
    "Horreur": "⚠️ Film dur",
    "Documentaire": "🧠 Complexe",
    "Histoire": "🎬 Classique",
    "Drame": "😢 Triste",
}

# Propriétés requises dans la base Notion -> type attendu (pour la validation au démarrage)
REQUIRED_PROPERTIES: Dict[str, str] = {
    Props.TITLE: "title",
    Props.TYPE: "select",
    Props.STATUS: "select",
    Props.SUPPORT: "select",
    Props.RELEASE_DATE: "date",
    Props.DIRECTOR: "rich_text",
    Props.CATEGORY: "multi_select",
    Props.SYNOPSIS: "rich_text",
    Props.TAGS: "multi_select",
    Props.TMDB_OK: "checkbox",
}


def validate_schema(db_properties: Dict[str, dict]) -> list[str]:
    """
    Compare les propriétés réelles de la base à REQUIRED_PROPERTIES.
    Retourne la liste des problèmes (vide si tout est conforme).
    """
    problems = []
    for name, expected_type in REQUIRED_PROPERTIES.items():
        prop = db_properties.get(name)
        if prop is None:
            problems.append(f"Propriété manquante : « {name} » (attendu : {expected_type})")
        elif prop.get("type") != expected_type:
            problems.append(
                f"Propriété « {name} » de type « {prop.get('type')} » "
                f"au lieu de « {expected_type} »"
            )
    return problems
