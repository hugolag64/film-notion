"""Optional, bounded Gemini assistance for the local recommendation engine."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

class GeminiSelection(BaseModel):
    tmdb_id: int
    confidence: float = Field(ge=0, le=1)
    reason: str = ""
    usage: dict[str, int] = Field(default_factory=dict)


class GeminiShortlist(BaseModel):
    tmdb_ids: list[int] = Field(default_factory=list)
    question_axes: list[str] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class GeminiRecommendationGateway:
    def __init__(
        self,
        api_key: str | None,
        model: str = "gemini-3.5-flash-lite",
        max_output_tokens: int = 256,
        client: Any | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.client = client
        self._types = None
        if self.client is None and api_key:
            try:
                from google import genai
                from google.genai import types
            except ImportError:  # pragma: no cover - deployment installs the pin
                return
            self._types = types
            self.client = genai.Client(api_key=api_key)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.client)

    @staticmethod
    def _compact_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "tmdb_id": int(candidate["tmdb_id"]),
                "title": candidate.get("title") or "",
                "overview": (candidate.get("overview") or "")[:400],
                "genre_ids": candidate.get("genre_ids") or [],
                "release_date": candidate.get("release_date"),
                "score": round(float(candidate.get("score") or 0), 4),
            }
            for candidate in candidates
        ]

    def _request(self, instruction: str, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
        if not self.enabled:
            raise RuntimeError("Gemini désactivé")
        prompt = json.dumps({"instruction": instruction, **payload}, ensure_ascii=False, separators=(",", ":"))
        if self._types is None:
            from types import SimpleNamespace
            config = SimpleNamespace(
                response_mime_type="application/json",
                max_output_tokens=self.max_output_tokens,
                temperature=0,
            )
        else:
            config = self._types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=self.max_output_tokens,
                temperature=0,
            )
        response = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Réponse Gemini vide")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Réponse Gemini invalide")
        metadata = getattr(response, "usage_metadata", None)
        usage = {
            "input_tokens": int(getattr(metadata, "prompt_token_count", 0) or 0),
            "output_tokens": int(getattr(metadata, "candidates_token_count", 0) or 0),
        }
        return parsed, usage

    @staticmethod
    def _validate_id(value: Any, candidates: list[dict[str, Any]]) -> int:
        try:
            tmdb_id = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Réponse Gemini sans ID TMDB valide") from error
        allowed = {int(candidate["tmdb_id"]) for candidate in candidates}
        if tmdb_id not in allowed:
            raise ValueError(f"ID TMDB non fourni par Backstage: {tmdb_id}")
        return tmdb_id

    def select_shortlist(self, profile: dict, candidates: list[dict]) -> GeminiShortlist | None:
        if not self.enabled:
            return None
        parsed, usage = self._request(
            "Sélectionne au plus 8 IDs TMDB parmi candidates et propose des axes de question.",
            {"profile": profile, "candidates": self._compact_candidates(candidates)},
        )
        raw_ids = parsed.get("tmdb_ids") or parsed.get("shortlist") or []
        tmdb_ids = [self._validate_id(value, candidates) for value in raw_ids[:8]]
        return GeminiShortlist(
            tmdb_ids=list(dict.fromkeys(tmdb_ids)),
            question_axes=[str(item) for item in (parsed.get("question_axes") or [])[:3]],
            usage=usage,
        )

    def select_final(
        self,
        profile: dict,
        answers: list[dict],
        candidates: list[dict],
    ) -> GeminiSelection | None:
        if not self.enabled:
            return None
        parsed, usage = self._request(
            "Choisis exactement un film parmi candidates. Retourne tmdb_id, confidence et une raison courte.",
            {
                "profile": profile,
                "answers": answers[-5:],
                "candidates": self._compact_candidates(candidates),
            },
        )
        return GeminiSelection(
            tmdb_id=self._validate_id(parsed.get("tmdb_id"), candidates),
            confidence=float(parsed.get("confidence", 0)),
            reason=str(parsed.get("reason") or ""),
            usage=usage,
        )
