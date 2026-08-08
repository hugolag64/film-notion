"""Pure, explainable recommendation scoring for Backstage."""

from datetime import datetime, timezone
from random import Random
from typing import Any

from pydantic import BaseModel, Field

from backend.core.models import Media, RecommendationEvent, UserMediaState
from backend.core.playback import PlaybackProgress
from backend.core.recommendation_explanations import build_recommendation_explanation


TMDB_GENRE_NAMES = {
    12: "Aventure", 14: "Fantastique", 16: "Animation", 18: "Drame",
    27: "Horreur", 28: "Action", 35: "Comédie", 36: "Histoire",
    37: "Western", 53: "Thriller", 80: "Crime", 99: "Documentaire",
    878: "Science-Fiction", 9648: "Mystère", 10402: "Musique",
    10749: "Romance", 10751: "Familial", 10752: "Guerre",
}

# Reverse lookup, used to turn a genre name (a session answer, or a name in the
# taste profile) back into the TMDB genre id a /discover query needs.
GENRE_IDS = {name: genre_id for genre_id, name in TMDB_GENRE_NAMES.items()}

SCORE_WEIGHTS = {
    "taste": 0.65,
    "session": 0.15,
    "tmdb_quality": 0.08,
    "list_bonus": 0.05,
    "novelty": 0.07,
}

# A dedicated weight for score_recommendation_candidate only — kept separate
# from SCORE_WEIGHTS["list_bonus"] (used by the legacy score_candidate) so
# this change doesn't perturb that function's own, already-documented
# calibration. An explicit watchlist/favorite marking is the strongest
# intent signal a user can give — meaningfully stronger than the durable
# taste-profile bonus deserves.
_INTENT_WEIGHT = 0.18


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


_STAR = "⭐"
_DONE_STATUSES = {"Terminé", "Terminée"}
_DEFAULT_NEUTRAL_RATING = 2.5  # midpoint of the 0-5 scale, used until the user has rated anything


def _rating_value(rating: str | None) -> float | None:
    """Parse a rating on the current /5 numeric scale, or the legacy /10
    star-emoji scale inherited from the Notion V1 import (e.g. "⭐️⭐️⭐️⭐️⭐️⭐️⭐️⭐️")."""
    if rating is None:
        return None
    text = str(rating).strip()
    if not text:
        return None
    stars = text.count(_STAR)
    if stars:
        return min(10, stars) / 2.0
    try:
        return max(0.0, min(5.0, float(text)))
    except (TypeError, ValueError):
        return None


def _add_signal(values: dict[str, list[float]], key: str, value: float) -> None:
    if key:
        values.setdefault(key, []).append(value)


def _verdict_signal(state: UserMediaState, mean_rating: float) -> float | None:
    """A verdict expresses what the user thought of a title, not merely that
    they intend to watch it. "À regarder" carries no verdict and must return
    None rather than a neutral 0 — a 0 would silently pull the genre's average
    toward "disliked" for every unrated, unwatched title in the catalogue."""
    rating = _rating_value(state.rating)
    if rating is not None:
        # Centered on the user's own average rating, not on an absolute 0,
        # so a 4/5 film reads as neutral for someone who rates everything 4+.
        return max(-1.0, min(1.0, (rating - mean_rating) / 2.5))
    if state.status == "A revoir":
        return 0.5  # the strongest signal available without a numeric rating
    if state.status in _DONE_STATUSES:
        return 0.1  # watched, but no opinion recorded
    return None


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

    ratings = [
        value for state in state_by_media.values()
        if (value := _rating_value(state.rating)) is not None
    ]
    mean_rating = sum(ratings) / len(ratings) if ratings else _DEFAULT_NEUTRAL_RATING

    for media_id, state in state_by_media.items():
        item = media_by_id.get(media_id)
        if not item:
            continue
        signal = _verdict_signal(state, mean_rating)
        if signal is None:
            continue
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


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def is_candidate_eligible(preference: dict[str, Any] | None, now: datetime) -> bool:
    if not preference:
        return True
    if preference.get("disposition") in {"hard_reject", "already_seen"}:
        return False
    # Temporary dispositions remain eligible for the durable profile; the
    # caller may lower their score until expires_at instead of banning them.
    return True


def apply_recommendation_signal(
    profile: TasteProfile,
    event_type: str,
    value: str | None,
    weight: float,
    now: datetime,
) -> TasteProfile:
    updated = profile.model_copy(deep=True)
    if event_type in {"shown", "skipped", "not_now", "already_seen", "hard_reject"} or not value:
        return updated
    current = updated.genre_affinity.get(value, 0.0)
    updated.genre_affinity[value] = round(max(-1.0, min(1.0, current + weight)), 4)
    return updated


_COMPARE_PICK_WEIGHT = 0.30
_COMPARE_REJECT_WEIGHT = -0.20


def record_compare_choice(
    session_preferences: dict[str, Any], picked_genre_ids: list[int], rejected_genre_ids: list[int],
) -> None:
    """Accumulate the genre delta from an A-vs-B movie_compare pick into
    session_preferences (mutated in place, JSON-serializable), so a later
    scoring pass in THIS session can prefer/avoid those genres. Genres shared
    by both films say nothing about that genre specifically and are left out
    of the penalty side. The durable, cross-session taste profile is never
    touched here — see apply_session_genre_delta."""
    delta: dict[str, float] = session_preferences.setdefault("genre_delta", {})
    all_picked_names = {TMDB_GENRE_NAMES.get(genre_id, str(genre_id)) for genre_id in picked_genre_ids}
    all_rejected_names = {TMDB_GENRE_NAMES.get(genre_id, str(genre_id)) for genre_id in rejected_genre_ids}
    picked_only_names = all_picked_names - all_rejected_names
    rejected_only_names = all_rejected_names - all_picked_names
    for name in picked_only_names:
        delta[name] = round(max(-1.0, min(1.0, delta.get(name, 0.0) + _COMPARE_PICK_WEIGHT)), 4)
    for name in rejected_only_names:
        delta[name] = round(max(-1.0, min(1.0, delta.get(name, 0.0) + _COMPARE_REJECT_WEIGHT)), 4)


def apply_session_genre_delta(
    profile: TasteProfile, session_preferences: dict[str, Any], now: datetime,
) -> TasteProfile:
    """Blend accumulated in-session compare choices (see record_compare_choice)
    into a COPY of the durable profile, for scoring only. The persisted,
    cross-session profile built from user_media_state is never mutated."""
    delta = session_preferences.get("genre_delta") or {}
    adjusted = profile
    for name, weight in delta.items():
        adjusted = apply_recommendation_signal(adjusted, "compare_choice", name, weight, now)
    return adjusted


def _candidate_field(candidate: dict[str, Any] | RecommendationCandidate, field: str, default: Any = None) -> Any:
    if isinstance(candidate, RecommendationCandidate):
        return getattr(candidate, field, default)
    return candidate.get(field, default)


def _known_genre_affinities(genres: list[str], profile: TasteProfile) -> list[float]:
    """Only genres the profile actually has an opinion on — a genre absent
    from genre_affinity is unknown, not neutral-zero, and must not dilute the
    average with genres the candidate happens to also carry."""
    return [profile.genre_affinity[genre] for genre in genres if genre in profile.genre_affinity]


def _taste_score(known_affinities: list[float], confidence: float) -> float:
    """Blend the strongest opinion (positive or negative) with the average of
    known genres, then remap from the affinity's [-1, 1] range into a [0, 1]
    taste contribution centered on neutral (0.5) — so a film in a loved genre
    plus several unrated ones still scores close to that loved genre alone,
    instead of being penalized for genres the profile has no opinion on."""
    if not known_affinities:
        return 0.5 * (1 - confidence)
    dominant = max(known_affinities, key=abs)
    average = sum(known_affinities) / len(known_affinities)
    blended = 0.65 * dominant + 0.35 * average
    return max(0.0, min(1.0, 0.5 + blended / 2))


def _novelty_score(genre_count: int, known_count: int, confidence: float) -> float:
    """The share of a candidate's genres the profile has no opinion on. A
    profile with no confidence yet cannot judge novelty either way."""
    if confidence <= 0:
        return 0.5
    if genre_count == 0:
        return 1.0
    return 1 - (known_count / genre_count)


def score_recommendation_candidate(
    candidate: dict[str, Any] | RecommendationCandidate,
    profile: TasteProfile,
    session_preferences: dict[str, Any],
    exclusions: dict[str, Any] | set[int] | None,
    now: datetime,
) -> RecommendationCandidate:
    tmdb_id = int(_candidate_field(candidate, "tmdb_id"))
    exclusions = {"seen_tmdb_ids": exclusions} if isinstance(exclusions, set) else (exclusions or {})
    if tmdb_id in set(exclusions.get("seen_tmdb_ids", set())) or tmdb_id in set(exclusions.get("hard_reject_tmdb_ids", set())):
        return RecommendationCandidate(
            tmdb_id=tmdb_id, title=_candidate_field(candidate, "title", "Sans titre") or "Sans titre", score=-1,
            overview=_candidate_field(candidate, "overview", "") or "", genre_ids=_candidate_field(candidate, "genre_ids", []) or [],
        )
    genre_ids = _candidate_field(candidate, "genre_ids", []) or []
    genres = [TMDB_GENRE_NAMES.get(genre_id, str(genre_id)) for genre_id in genre_ids]
    known_affinities = _known_genre_affinities(genres, profile)
    taste = _taste_score(known_affinities, profile.confidence)
    session = 1 if session_preferences.get("genre") in genres else 0
    if tmdb_id in session_preferences.get("preferred_tmdb_ids", []):
        session = 1
    if session_preferences.get("mood") == "light" and "Comédie" in genres:
        session += 0.5
    if session_preferences.get("mood") == "intense" and any(genre in genres for genre in ("Thriller", "Action", "Horreur")):
        session += 0.5
    session = min(1, session)
    quality = min(1, max(0, float(_candidate_field(candidate, "vote_average", 0) or 0) / 10))
    intent = 1 if tmdb_id in set(exclusions.get("watchlisted_tmdb_ids", set())) else 0
    novelty = _novelty_score(len(genres), len(known_affinities), profile.confidence)
    exploration = 0.09 if profile.confidence else 0.18
    temporary_penalty = float(exclusions.get("temporary_negative_tmdb_ids", {}).get(tmdb_id, 0))
    score = (
        SCORE_WEIGHTS["taste"] * taste + (SCORE_WEIGHTS["session"] + 0.07) * session
        + SCORE_WEIGHTS["tmdb_quality"] * quality + _INTENT_WEIGHT * intent
        + SCORE_WEIGHTS["novelty"] * novelty + exploration * novelty - temporary_penalty
    )
    reasons = ["not_seen"]
    # Calibrated to the centered affinity scale (roughly ±0.5 in practice, not
    # ±1): 0.25 already means "meaningfully above this user's own neutral point".
    if known_affinities and max(known_affinities) >= 0.25:
        reasons.insert(0, "genre_match")
    if intent:
        reasons.append("watchlist_bonus")
    if session:
        reasons.append("session_match")
    if novelty >= 0.75:
        reasons.append("discovery_pick")
    reasons.append("exploration")
    explanation = build_recommendation_explanation(
        {
            "title": _candidate_field(candidate, "title", "Sans titre") or "Sans titre",
            "genre_names": genres,
            "vote_average": _candidate_field(candidate, "vote_average", 0),
            "reasons": reasons,
            "tmdb_id": tmdb_id,
        },
        profile,
        session_preferences,
    )
    recommendation = RecommendationCandidate(
        tmdb_id=tmdb_id, title=_candidate_field(candidate, "title", "Sans titre") or "Sans titre",
        overview=_candidate_field(candidate, "overview", "") or "", score=round(score, 6), reasons=reasons,
        genre_ids=genre_ids, poster_path=_candidate_field(candidate, "poster_path"),
        backdrop_path=_candidate_field(candidate, "backdrop_path"), release_date=_candidate_field(candidate, "release_date"),
        vote_average=float(_candidate_field(candidate, "vote_average", 0) or 0),
    )
    object.__setattr__(recommendation, "explanation", explanation)
    return recommendation


def build_adaptive_question(
    candidates: list[dict[str, Any] | RecommendationCandidate],
    profile: TasteProfile,
    session_preferences: dict[str, Any],
) -> dict[str, Any] | None:
    eligible = [item for item in candidates if float(_candidate_field(item, "score", 0) or 0) >= 0]
    if not eligible:
        return None
    ordered = sorted(eligible, key=lambda item: float(_candidate_field(item, "score", 0) or 0), reverse=True)
    first = ordered[0]
    first_genres = set(_candidate_field(first, "genre_ids", []) or [])
    second = next((item for item in ordered[1:] if not first_genres.intersection(_candidate_field(item, "genre_ids", []) or [])), None)
    second = second or (ordered[1] if len(ordered) > 1 else None)

    def serialize(item: dict[str, Any] | RecommendationCandidate) -> dict[str, Any]:
        if isinstance(item, RecommendationCandidate):
            return item.model_dump(mode="json")
        return score_recommendation_candidate(item, profile, session_preferences, {}, datetime.now(timezone.utc)).model_dump(mode="json")

    options = [serialize(first)] + ([serialize(second)] if second else [])
    return {
        "type": "compare" if len(options) == 2 else "single",
        "prompt": "Tu préfères lequel ?" if len(options) == 2 else "Voici une piste pour toi.",
        "options": options,
    }


def build_local_question(
    axis: str,
    candidates: list[RecommendationCandidate],
    profile: TasteProfile,
    session_preferences: dict[str, Any],
) -> dict[str, Any] | None:
    eligible = [item for item in candidates if item.score >= 0]
    if axis == "movie_compare":
        ordered = sorted(eligible, key=lambda item: item.score, reverse=True)
        if not ordered:
            return None
        first = ordered[0]
        second = next(
            (item for item in ordered[1:] if not set(first.genre_ids).intersection(item.genre_ids)),
            ordered[1] if len(ordered) > 1 else None,
        )
        options = [first] + ([second] if second else [])
        return {
            "type": "compare" if len(options) == 2 else "single",
            "axis": axis,
            "prompt": "Tu préfères lequel ?" if len(options) == 2 else "Cette piste te tente ?",
            "options": [item.model_dump(mode="json") for item in options],
        }
    if axis == "mood":
        return {
            "type": "choice",
            "axis": axis,
            "prompt": "Quelle ambiance tu cherches ?",
            "options": [
                {"answer": "light", "label": "Quelque chose de léger", "description": "Comédie, aventure ou feel-good"},
                {"answer": "intense", "label": "Quelque chose d'intense", "description": "Tension, émotion ou atmosphère forte"},
                {"answer": "surprise", "label": "Surprends-moi", "description": "Je te laisse choisir"},
            ],
        }
    if axis == "genre":
        genre_names: list[str] = []
        for item in eligible:
            for genre_id in item.genre_ids:
                genre = TMDB_GENRE_NAMES.get(genre_id)
                if genre and genre not in genre_names:
                    genre_names.append(genre)
        options = genre_names[:4]
        if len(options) < 2:
            return None
        return {
            "type": "choice",
            "axis": axis,
            "prompt": "Vers quel univers tu veux aller ?",
            "options": [
                {"answer": f"genre:{genre}", "label": genre, "description": "Voir des films de cet univers"}
                for genre in options
            ],
        }
    if axis == "era":
        return {
            "type": "choice",
            "axis": axis,
            "prompt": "Quelle période te fait envie ?",
            "options": [
                {"answer": "era:recent", "label": "Récent", "description": "Les sorties des dernières années"},
                {"answer": "era:classic", "label": "Classique", "description": "Un film qui a déjà marqué son époque"},
                {"answer": "era:surprise", "label": "Sans préférence", "description": "Laisse parler la recommandation"},
            ],
        }
    return None


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
