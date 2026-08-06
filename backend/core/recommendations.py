"""Pure, explainable recommendation scoring for Backstage."""

from datetime import datetime, timezone
from random import Random
from typing import Any

from pydantic import BaseModel, Field

from backend.core.models import Media, RecommendationEvent, UserMediaState
from backend.core.playback import PlaybackProgress


TMDB_GENRE_NAMES = {
    12: "Aventure", 14: "Fantastique", 16: "Animation", 18: "Drame",
    27: "Horreur", 28: "Action", 35: "Comédie", 36: "Histoire",
    37: "Western", 53: "Thriller", 80: "Crime", 99: "Documentaire",
    878: "Science-Fiction", 9648: "Mystère", 10402: "Musique",
    10749: "Romance", 10751: "Familial", 10752: "Guerre",
}

SCORE_WEIGHTS = {
    "taste": 0.65,
    "session": 0.15,
    "tmdb_quality": 0.08,
    "list_bonus": 0.05,
    "novelty": 0.07,
}


class TasteProfile(BaseModel):
    genre_affinity: dict[str, float] = Field(default_factory=dict)
    keyword_affinity: dict[str, float] = Field(default_factory=dict)
    director_affinity: dict[str, float] = Field(default_factory=dict)
    actor_affinity: dict[str, float] = Field(default_factory=dict)
    preferred_runtime_minutes: tuple[int, int] | None = None
    confidence: float = 0


class RecommendationCandidate(BaseModel):
    tmdb_id: int
    title: str
    overview: str = ""
    score: float
    reasons: list[str] = Field(default_factory=list)
    genre_ids: list[int] = Field(default_factory=list)
    poster_path: str | None = None
    backdrop_path: str | None = None
    release_date: str | None = None
    vote_average: float = 0


def _rating_value(rating: str | None) -> float | None:
    if rating is None:
        return None
    try:
        return max(0, min(5, float(rating)))
    except (TypeError, ValueError):
        return None


def _add_signal(values: dict[str, list[float]], key: str, value: float) -> None:
    if key:
        values.setdefault(key, []).append(value)


def build_taste_profile(
    media: list[Media],
    user_states: list[UserMediaState],
    playback: list[PlaybackProgress],
    events: list[RecommendationEvent],
    now: datetime,
) -> TasteProfile:
    media_by_id = {item.id: item for item in media}
    state_by_media = {state.media_id: state for state in user_states}
    genre_values: dict[str, list[float]] = {}
    director_values: dict[str, list[float]] = {}
    actor_values: dict[str, list[float]] = {}
    signals = 0
    runtimes: list[int] = []

    for media_id, state in state_by_media.items():
        item = media_by_id.get(media_id)
        if not item:
            continue
        rating = _rating_value(state.rating)
        signal = rating / 5 if rating is not None else (0.65 if state.status in {"Terminé", "Terminée"} else 0)
        if state.status in {"Terminé", "Terminée"} or rating is not None:
            signals += 1
        for genre in item.categories:
            _add_signal(genre_values, genre, signal)
        _add_signal(director_values, item.director or "", signal)
        for actor in item.cast:
            _add_signal(actor_values, actor, signal)

    for progress in playback:
        item = media_by_id.get(progress.media_id or "")
        if not item:
            continue
        signal = 0.8 if progress.played or progress.percent >= 90 else (-0.25 if progress.percent < 20 else 0.15)
        for genre in item.categories:
            _add_signal(genre_values, genre, signal)
        signals += 1

    for event in events:
        item = media_by_id.get(event.media_id or "")
        if not item:
            continue
        signal = 0.35 if event.event_type == "more_like_this" else -0.45 if event.event_type == "less_like_this" else 0
        for genre in item.categories:
            _add_signal(genre_values, genre, signal)

    def averages(values: dict[str, list[float]]) -> dict[str, float]:
        return {key: round(sum(items) / len(items), 4) for key, items in values.items() if items}

    confidence = min(1, signals / 8)
    return TasteProfile(
        genre_affinity=averages(genre_values),
        director_affinity=averages(director_values),
        actor_affinity=averages(actor_values),
        confidence=confidence,
    )


def score_candidate(
    candidate: dict[str, Any],
    profile: TasteProfile,
    session_preferences: dict[str, Any],
    seen_tmdb_ids: set[int],
    watchlisted_tmdb_ids: set[int],
    now: datetime,
) -> RecommendationCandidate:
    tmdb_id = int(candidate["tmdb_id"])
    if tmdb_id in seen_tmdb_ids:
        return RecommendationCandidate(
            tmdb_id=tmdb_id, title=candidate.get("title") or "Sans titre", score=-1,
            overview=candidate.get("overview") or "", genre_ids=candidate.get("genre_ids") or [],
        )
    genres = [TMDB_GENRE_NAMES.get(genre_id, str(genre_id)) for genre_id in candidate.get("genre_ids") or []]
    matching_affinities = [profile.genre_affinity.get(genre, 0) for genre in genres]
    taste = sum(matching_affinities) / len(matching_affinities) if matching_affinities else 0.5 * (1 - profile.confidence)
    session_genre = session_preferences.get("genre")
    session = 1 if session_genre and session_genre in genres else 0
    if tmdb_id in session_preferences.get("preferred_tmdb_ids", []):
        session = 1
    if session_preferences.get("mood") == "light" and "Comédie" in genres:
        session += 0.5
    if session_preferences.get("mood") == "intense" and any(genre in genres for genre in ("Thriller", "Action", "Horreur")):
        session += 0.5
    session = min(1, session)
    quality = min(1, max(0, float(candidate.get("vote_average") or 0) / 10))
    list_bonus = 1 if tmdb_id in watchlisted_tmdb_ids else 0
    novelty = 1 if profile.confidence > 0 and not matching_affinities else 0.5
    score = (
        SCORE_WEIGHTS["taste"] * taste
        + SCORE_WEIGHTS["session"] * session
        + SCORE_WEIGHTS["tmdb_quality"] * quality
        + SCORE_WEIGHTS["list_bonus"] * list_bonus
        + SCORE_WEIGHTS["novelty"] * novelty
    )
    reasons = []
    if matching_affinities and max(matching_affinities) >= 0.7:
        reasons.append("genre_match")
    if list_bonus:
        reasons.append("watchlist_bonus")
    if session:
        reasons.append("session_match")
    if novelty >= 1:
        reasons.append("discovery_pick")
    reasons.append("not_seen")
    return RecommendationCandidate(
        tmdb_id=tmdb_id,
        title=candidate.get("title") or "Sans titre",
        overview=candidate.get("overview") or "",
        score=round(score, 6),
        reasons=reasons,
        genre_ids=candidate.get("genre_ids") or [],
        poster_path=candidate.get("poster_path"),
        backdrop_path=candidate.get("backdrop_path"),
        release_date=candidate.get("release_date"),
        vote_average=float(candidate.get("vote_average") or 0),
    )


def choose_from_top(
    candidates: list[RecommendationCandidate],
    rng: Random,
    top_n: int = 8,
) -> RecommendationCandidate | None:
    eligible = sorted((item for item in candidates if item.score >= 0), key=lambda item: item.score, reverse=True)[:top_n]
    if not eligible:
        return None
    weights = [max(0.05, item.score) for item in eligible]
    return rng.choices(eligible, weights=weights, k=1)[0]
