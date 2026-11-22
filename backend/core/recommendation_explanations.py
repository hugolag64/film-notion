"""Local, deterministic French explanations for recommendation cards.

The sentence bank deliberately lives in the application instead of calling an
LLM for every card.  Openers and closers are combined deterministically from
the TMDB id, yielding more than a hundred natural variants while keeping the
dashboard fast and token-free.
"""

from random import Random
from typing import Any


_GENRE_OPENERS = (
    "{title} s'inscrit dans le genre {genre} que tu apprécies",
    "J'ai retenu {title} pour son approche du {genre}",
    "{title} reprend les codes du {genre} que tu notes souvent très bien",
    "Cette piste, {title}, rejoint ton goût pour le {genre}",
    "Ton intérêt pour le {genre} m'a orienté vers {title}",
    "{title} devrait te parler si tu recherches encore du {genre}",
    "Le profil de {title} correspond à ta préférence pour le {genre}",
    "{title} mélange une vraie identité et les ingrédients du {genre}",
    "Pour prolonger ton parcours dans le {genre}, voici {title}",
    "{title} a été choisi comme prolongement naturel de tes films de {genre}",
    "Le {genre} est au cœur de {title}, ce qui colle à tes préférences",
    "{title} ressort de ta sélection grâce à son affinité avec le {genre}",
)

_QUALITY_CLOSERS = (
    "La communauté TMDB lui attribue {rating}/10",
    "Son accueil utilisateurs TMDB atteint {rating}/10",
    "TMDB confirme la piste avec une note de {rating}/10",
    "Les utilisateurs TMDB lui donnent {rating}/10",
    "Sa note TMDB de {rating}/10 en fait une découverte solide",
    "Avec {rating}/10 sur TMDB, le choix mérite ton attention",
    "Le score TMDB de {rating}/10 renforce cette recommandation",
    "Les votes TMDB placent ce film à {rating}/10",
    "Sa réception sur TMDB est bonne, avec {rating}/10",
    "Le public TMDB l'a évalué à {rating}/10",
)

_SESSION_OPENERS = (
    "{title} répond directement à ce que tu recherches en ce moment",
    "Pour cette sélection, {title} est une piste particulièrement cohérente",
    "{title} colle à l'envie que tu viens d'exprimer",
    "J'ai rapproché ton choix actuel de {title}",
    "Cette sélection t'emmène vers {title}, dans la direction que tu as choisie",
    "{title} a été retenu pour prolonger ta recherche du moment",
    "Ton choix de séance fait ressortir {title}",
    "Voici {title}, une réponse ciblée à ta sélection actuelle",
)

_SESSION_CLOSERS = (
    "C'est une piste ciblée, pas un choix au hasard",
    "La sélection TMDB confirme cette compatibilité",
    "Le film garde toutefois une part de découverte",
    "Il combine ton intention du moment avec une proposition nouvelle",
    "Il complète ta sélection sans répéter exactement ce que tu connais déjà",
    "C'est le compromis entre tes critères et une vraie découverte",
    "Le résultat reste personnel tout en profitant du catalogue TMDB",
    "Cette association est issue de tes réponses et du classement TMDB",
)

_DISCOVERY_OPENERS = (
    "{title} est une découverte qui peut élargir ton horizon",
    "Je te propose {title} pour sortir légèrement de tes habitudes",
    "{title} apporte une variation intéressante à ta bibliothèque",
    "Cette fois, place à la découverte avec {title}",
    "{title} n'est pas le choix le plus évident, et c'est précisément son intérêt",
    "Pour varier les plaisirs, je te suggère {title}",
    "{title} ouvre une nouvelle piste dans ton parcours de spectateur",
    "Voici une proposition plus exploratoire : {title}",
)

_GENERIC_OPENERS = (
    "{title} ressort comme une piste équilibrée",
    "La sélection TMDB fait ressortir {title}",
    "{title} mérite une place dans tes prochaines découvertes",
    "Cette recommandation met en avant {title}",
    "{title} complète bien les possibilités de ta bibliothèque",
    "Je garde {title} dans ta sélection pour une bonne raison",
)


def _rating(candidate: dict[str, Any]) -> str:
    value = candidate.get("vote_average")
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _finish(sentence: str) -> str:
    sentence = sentence.strip()
    return sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."


def is_readable_title(title: str | None) -> bool:
    """False for titles with no Latin letter at all (Arabic, CJK, Cyrillic…):
    TMDB sometimes has no French title and falls back to the original one,
    which a French-speaking household cannot read."""
    import unicodedata

    return any(
        char.isalpha() and "LATIN" in unicodedata.name(char, "")
        for char in (title or "")
    )


_MOOD_LABELS = {
    "light": "léger ou drôle",
    "intense": "prenant",
    "moving": "émouvant",
    "thoughtful": "qui fait réfléchir",
}

# Genres that really prove a mood in the sentence.  The candidate pool uses
# wider MOOD_GENRES (Animation counts as "light"), but an animated horror film
# must not be described as light or funny.
_MOOD_PROOF = {
    "light": ("Comédie", "Familial"),
}


def _french_number(value: Any) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"{number:.1f}".replace(".", ",") if number > 0 else None


def build_guided_explanation(candidate: dict[str, Any], preferences: dict[str, Any]) -> str:
    """Explain a guided pick from the user's own answers, mentioning only the
    criteria the film really matches (used when the LLM gives no reason)."""
    from backend.core.guided_recommendations import MOOD_GENRES, _REFINEMENTS
    from backend.core.recommendations import TMDB_GENRE_NAMES

    title = candidate.get("title") or "Ce film"
    year = str(candidate.get("release_date") or "")[:4]
    genres = {TMDB_GENRE_NAMES.get(genre_id) for genre_id in candidate.get("genre_ids") or []} - {None}

    matched: list[str] = []
    for genre in preferences.get("genres") or []:
        if genre in genres:
            matched.append(genre.lower())
    refinement = preferences.get("refinement")
    if refinement and refinement in genres:
        # Same value, different label per genre ("Mystère" = "Une énigme" for
        # science-fiction, "Une enquête" for thriller): use the asked genre.
        label = next(
            (choice_label for genre in preferences.get("genres") or [] if genre in _REFINEMENTS
             for value, choice_label in _REFINEMENTS[genre][1] if value == refinement),
            refinement,
        )
        matched.append(label[0].lower() + label[1:])
    mood = preferences.get("mood")
    if mood in _MOOD_LABELS and genres.intersection(_MOOD_PROOF.get(mood) or MOOD_GENRES.get(mood, ())):
        matched.append(_MOOD_LABELS[mood])

    named = f"{title} ({year})" if year.isdigit() else title
    rating = _french_number(candidate.get("vote_average"))
    rating_sentence = f" Le public le note {rating}/10." if rating else ""
    if matched:
        criteria = ", ".join(matched[:-1]) + (" et " if len(matched) > 1 else "") + matched[-1]
        return f"Tu cherchais : {criteria}. {named} coche ces cases.{rating_sentence}"
    return (
        f"Petit écart volontaire : {named} change un peu de tes critères, "
        f"pour ne pas te proposer toujours la même chose.{rating_sentence}"
    )


def build_recommendation_explanation(
    candidate: dict[str, Any], profile: Any, session_preferences: dict[str, Any],
) -> str:
    """Return one user-facing explanation without exposing scoring internals."""
    title = candidate.get("title") or "Ce film"
    genres = [genre for genre in candidate.get("genre_names", []) if genre]
    affinities = getattr(profile, "genre_affinity", {}) or {}
    preferred = sorted(
        (genre for genre in genres if genre in affinities),
        key=lambda genre: affinities[genre],
        reverse=True,
    )
    genre = preferred[0] if preferred else (genres[0] if genres else "cinéma")
    rating = _rating(candidate)
    seed = int(candidate.get("tmdb_id") or 0)
    rng = Random(seed)
    reasons = set(candidate.get("reasons") or [])

    if "genre_match" in reasons and preferred:
        opener = rng.choice(_GENRE_OPENERS).format(title=title, genre=genre)
        closer = rng.choice(_QUALITY_CLOSERS).format(rating=rating)
        return _finish(f"{opener}. {closer}")
    if "session_match" in reasons or session_preferences.get("genre"):
        opener = rng.choice(_SESSION_OPENERS).format(title=title)
        closer = rng.choice(_SESSION_CLOSERS)
        return _finish(f"{opener}. {closer}")
    if "discovery_pick" in reasons or "exploration" in reasons:
        return _finish(rng.choice(_DISCOVERY_OPENERS).format(title=title))
    return _finish(rng.choice(_GENERIC_OPENERS).format(title=title))
