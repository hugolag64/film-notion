"""Règles pures de la soirée film : questions, combinaison des réponses, vote, expiration."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from backend.core.recommendations import TasteProfile

PARTY_TTL = timedelta(hours=3)
ACTIVE_STATUSES = ("joining", "voting")

_ANY = {"value": "any", "label": "Peu importe"}
_MOOD = {
    "key": "mood", "label": "Quelle humeur ?",
    "options": [{"value": "light", "label": "Léger"}, {"value": "intense", "label": "Intense"}, _ANY],
}
_RUNTIME = {
    "key": "runtime", "label": "Combien de temps ?",
    "options": [{"value": "105", "label": "1 h 45"}, {"value": "135", "label": "2 h 15"}, _ANY],
}
_ERA = {
    "key": "era", "label": "Quelle époque ?",
    "options": [{"value": "recent", "label": "Plutôt récent"}, {"value": "classic", "label": "Plutôt classique"}, _ANY],
}
QUESTIONS: dict[str, list[dict]] = {"coloc": [_MOOD, _RUNTIME, _ERA], "cinema": [_MOOD, _RUNTIME]}


def validate_answers(mode: str, answers: dict) -> dict:
    if mode not in QUESTIONS:
        raise ValueError(f"Mode inconnu : {mode}")
    valid: dict[str, str] = {}
    for question in QUESTIONS[mode]:
        value = (answers or {}).get(question["key"])
        if value not in {option["value"] for option in question["options"]}:
            raise ValueError(f"Réponse invalide pour « {question['label']} »")
        valid[question["key"]] = value
    return valid


def _majority(values: list[str]) -> str:
    counts = Counter(value for value in values if value and value != "any").most_common()
    if not counts or (len(counts) > 1 and counts[0][1] == counts[1][1]):
        return "any"
    return counts[0][0]


def combine_answers(answers: list[dict]) -> dict:
    runtimes = [int(a["runtime"]) for a in answers if str(a.get("runtime", "")).isdigit()]
    return {
        "mood": _majority([a.get("mood") for a in answers]),
        "runtime_max": min(runtimes) if runtimes else None,
        "era": _majority([a.get("era") for a in answers]),
    }


def _average(dicts: list[dict[str, float]]) -> dict[str, float]:
    keys = {key for values in dicts for key in values}
    return {key: sum(values.get(key, 0.0) for values in dicts) / len(dicts) for key in sorted(keys)}


def average_profiles(profiles: list[TasteProfile]) -> TasteProfile:
    if not profiles:
        return TasteProfile()
    return TasteProfile(
        genre_affinity=_average([p.genre_affinity for p in profiles]),
        keyword_affinity=_average([p.keyword_affinity for p in profiles]),
        director_affinity=_average([p.director_affinity for p in profiles]),
        actor_affinity=_average([p.actor_affinity for p in profiles]),
        preferred_runtime_minutes=None,
        confidence=sum(p.confidence for p in profiles) / len(profiles),
    )


def tally(proposals: list[dict], votes: list[dict]) -> dict:
    scores = {p["rank"]: {"up": 0, "down": 0} for p in proposals}
    for vote in votes:
        if vote["rank"] in scores:
            scores[vote["rank"]]["up" if vote["value"] > 0 else "down"] += 1
    winner = None
    if scores:
        winner = min(scores, key=lambda rank: (-(scores[rank]["up"] - scores[rank]["down"]), rank))
    return {"scores": scores, "winner_rank": winner}


def is_expired(party: dict, now: datetime) -> bool:
    return party["status"] in ACTIVE_STATUSES and now - party["created_at"] >= PARTY_TTL
