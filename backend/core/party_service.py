"""Soirée film : lancement, partants, propositions, votes et bot « Soirée » du salon."""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.config import Config
from backend.core.cinema_store import CinemaStore
from backend.core.cinema_sync import reunion_now
from backend.core.gemini_recommendations import GeminiRecommendationGateway
from backend.core.party_candidates import TOP_N, cinema_candidates, coloc_candidates, pick_three
from backend.core.party_logic import (
    PARTY_TTL, QUESTIONS, average_profiles, combine_answers, is_expired, tally, validate_answers,
)
from backend.core.party_store import PartyStore
from backend.core.recommendations import build_taste_profile
from backend.core.store import MediaStore
from backend.core.tmdb import TMDBClient

logger = logging.getLogger(__name__)

BOT_ID = "bot:soiree"
BOT_NAME = "Soirée"
MODES = {"coloc": "Coloc", "cinema": "ciné"}
_DONE_STATUSES = {"Terminé", "Terminée"}
_COMMAND_RE = re.compile(r"^@soiree(?=\s|$)(.*)$", re.DOTALL)
HELP_COMMANDS = [
    {"command": "@soirée coloc", "description": "Un film à la coloc, sur le serveur ou à demander."},
    {"command": "@soirée ciné", "description": "Une séance ce soir au Grand Sud."},
]
EMPTY_MESSAGES = {
    "cinema": "Plus de séance ce soir au Grand Sud qui vous convienne.",
    "coloc": "Pas de film trouvé pour ce soir.",
}


class _NoTMDB:
    """TMDB non configuré : chaque appel échoue comme une panne, que les candidats tolèrent."""

    async def discover_movies(self, **kwargs):
        raise ValueError("TMDB indisponible")

    async def get_movie_details(self, tmdb_id):
        raise ValueError("TMDB indisponible")


class PartyError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def default_gateway() -> GeminiRecommendationGateway:
    return GeminiRecommendationGateway(Config.GEMINI_API_KEY, Config.GEMINI_MODEL)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def is_party_command(body: str) -> bool:
    return _COMMAND_RE.match(_fold((body or "").strip())) is not None


def _name(user: dict) -> str:
    return user.get("display_name") or "Anonyme"


class PartyService:
    def __init__(
        self,
        store: MediaStore,
        *,
        tmdb_factory: Callable[[], Any] = TMDBClient,
        gateway_factory: Callable[[], Any] = default_gateway,
        clock: Callable[[], datetime] = reunion_now,
    ):
        self.store = store
        self.parties = PartyStore(store.db_path)
        self.tmdb_factory = tmdb_factory
        self.gateway_factory = gateway_factory
        self.clock = clock

    # --- Lecture ------------------------------------------------------------

    async def _party(self, party_id: str) -> dict:
        party = await self.parties.get_party(party_id)
        if party is None:
            raise PartyError(404, "Soirée inconnue.")
        if is_expired(party, self.clock()):
            await self.parties.set_status(party_id, "expired", at=self.clock())
            party = await self.parties.get_party(party_id)
        return party

    async def _member(self, party_id: str, user: dict) -> dict:
        member = next((m for m in await self.parties.list_members(party_id) if m["user_id"] == user["id"]), None)
        if member is None:
            raise PartyError(403, "Tu n'es pas dans cette soirée.")
        return member

    @staticmethod
    def _require_status(party: dict, *statuses: str) -> None:
        if party["status"] not in statuses:
            raise PartyError(409, "Cette étape de la soirée est terminée.")

    @staticmethod
    def _require_starter(party: dict, user: dict) -> None:
        if party["starter_id"] != user["id"]:
            raise PartyError(403, "Seul celui qui a lancé la soirée peut faire ça.")

    async def state(self, party_id: str, viewer_id: str) -> dict:
        party = await self._party(party_id)
        members = await self.parties.list_members(party_id)
        proposals = await self.parties.list_proposals(party_id)
        votes = await self.parties.list_votes(party_id)
        result = tally(proposals, votes)
        me = next((m for m in members if m["user_id"] == viewer_id), None)
        return {
            "id": party["id"],
            "mode": party["mode"],
            "status": party["status"],
            "starter": {"id": party["starter_id"], "name": party["starter_name"]},
            "questions": QUESTIONS[party["mode"]],
            "members": [
                {"name": m["display_name"], "answered": m["answers"] is not None, "late": m["late"]} for m in members
            ],
            "me": {
                "member": me is not None,
                "answered": bool(me and me["answers"] is not None),
                "starter": party["starter_id"] == viewer_id,
                "votes": {v["rank"]: v["value"] for v in votes if v["user_id"] == viewer_id},
            },
            "proposals": [
                {key: p[key] for key in ("rank", "tmdb_id", "title", "poster_url", "reason", "source", "showtime")}
                for p in proposals
            ],
            "scores": result["scores"],
            "winner_rank": result["winner_rank"] if party["status"] == "done" else None,
            "expires_at": (party["created_at"] + PARTY_TTL).isoformat(),
        }

    # --- Actions ------------------------------------------------------------

    async def _bot_say(self, body: str, payload: Optional[dict] = None, visible_to: Optional[str] = None) -> dict:
        return await self.store.create_chat_message(
            BOT_ID, BOT_NAME, None, body, payload=payload, visible_to=visible_to,
        )

    async def start(self, user: dict, mode: str) -> dict:
        if mode not in MODES:
            raise PartyError(422, "Mode de soirée inconnu.")
        now = self.clock()
        active = await self.parties.active_party()
        if active is not None:
            if is_expired(active, now):
                await self.parties.set_status(active["id"], "expired", at=now)
            else:
                raise PartyError(409, "Une soirée est déjà en cours.")
        party_id = str(uuid.uuid4())
        await self.parties.create_party(party_id, mode, user["id"], _name(user), now)
        await self.parties.add_member(party_id, user["id"], _name(user), now, late=False)
        message = await self._bot_say(
            f"🍿 {_name(user)} lance une soirée {MODES[mode]} ! Qui est partant ?",
            {"type": "party", "party_id": party_id},
        )
        await self.parties.set_message_id(party_id, message["id"])
        return await self.state(party_id, user["id"])

    async def join(self, party_id: str, user: dict) -> dict:
        party = await self._party(party_id)
        self._require_status(party, "joining", "voting")
        await self.parties.add_member(party_id, user["id"], _name(user), self.clock(), late=party["status"] == "voting")
        return await self.state(party_id, user["id"])

    async def answer(self, party_id: str, user: dict, answers: dict) -> dict:
        party = await self._party(party_id)
        await self._member(party_id, user)
        self._require_status(party, "joining")
        try:
            valid = validate_answers(party["mode"], answers)
        except ValueError as error:
            raise PartyError(422, str(error)) from error
        await self.parties.set_answers(party_id, user["id"], valid)
        return await self.state(party_id, user["id"])

    async def _member_profile_and_seen(self, user_id: str, medias: list) -> tuple[Any, set[int]]:
        states = await self.store.list_user_media_states(user_id)
        playback = await self.store.list_resume_progress(user_id) + await self.store.list_recently_completed(user_id)
        events = await self.store.list_recommendation_events(user_id)
        profile = build_taste_profile(medias, states, playback, events, datetime.now(timezone.utc))
        by_id = {media.id: media for media in medias}
        seen = set(await self.store.list_diary_tmdb_ids(user_id))
        for state in states:
            media = by_id.get(state.media_id)
            if media and media.tmdb_id and (state.status in _DONE_STATUSES or str(state.rating or "").strip()):
                seen.add(media.tmdb_id)
        for progress in playback:
            media = by_id.get(progress.media_id)
            if media and media.tmdb_id and (progress.played or progress.percent >= 95):
                seen.add(media.tmdb_id)
        return profile, seen

    async def _gemini_pick(self, profile, combined: dict, candidates: list[dict]):
        gateway = self.gateway_factory()
        if not getattr(gateway, "enabled", False):
            return None
        try:
            # Gemini ne choisit que parmi des films identifiés (un film du ciné peut ne pas l'être).
            known = [c for c in candidates[:TOP_N] if c.get("tmdb_id")]
            if len(known) < 3:
                return None
            return await asyncio.to_thread(gateway.select_group, profile.model_dump(mode="json"), combined, known)
        except Exception as error:  # Gemini est une aide : le classement local suffit.
            logger.warning("[soirée] Gemini indisponible : %s", error)
            return None

    async def launch(self, party_id: str, user: dict) -> dict:
        party = await self._party(party_id)
        self._require_starter(party, user)
        now = self.clock()
        if not await self.parties.set_status(party_id, "voting", at=now):
            raise PartyError(409, "La soirée est déjà lancée.")
        try:
            proposals = await self._propose(party, now)
        except Exception:  # Une panne ne doit pas bloquer la coloc pendant 3 h.
            logger.exception("[soirée] Lancement impossible")
            proposals = []
        if not proposals:
            await self.parties.set_status(party_id, "empty", at=now)
            await self._bot_say(EMPTY_MESSAGES[party["mode"]])
            return await self.state(party_id, user["id"])
        await self.parties.replace_proposals(party_id, proposals)
        return await self.state(party_id, user["id"])

    def _tmdb(self):
        try:
            return self.tmdb_factory()
        except ValueError as error:
            logger.warning("[soirée] TMDB indisponible : %s", error)
            return _NoTMDB()

    async def _propose(self, party: dict, now: datetime) -> list[dict]:
        members = await self.parties.list_members(party["id"])
        answered = [m for m in members if m["answers"] is not None] or members
        medias = await self.store.fetch_all()
        profiles, seen = [], set()
        for member in members:
            profile, member_seen = await self._member_profile_and_seen(member["user_id"], medias)
            seen |= member_seen
            if member in answered:
                profiles.append(profile)
        profile = average_profiles(profiles)
        combined = combine_answers([m["answers"] for m in answered if m["answers"]])
        tmdb = self._tmdb()
        if party["mode"] == "cinema":
            candidates = await cinema_candidates(CinemaStore(self.store.db_path), tmdb, profile, combined, now)
        else:
            candidates = await coloc_candidates(self.store, tmdb, profile, combined, seen, now)
        if not candidates:
            return []
        pick = await self._gemini_pick(profile, combined, candidates)
        return pick_three(candidates, pick)

    async def vote(self, party_id: str, user: dict, rank: int, value: int) -> dict:
        party = await self._party(party_id)
        await self._member(party_id, user)
        self._require_status(party, "voting")
        if value not in (1, -1):
            raise PartyError(422, "Vote invalide.")
        proposals = await self.parties.list_proposals(party_id)
        if rank not in {p["rank"] for p in proposals}:
            raise PartyError(422, "Proposition inconnue.")
        await self.parties.set_vote(party_id, user["id"], rank, value)
        members = await self.parties.list_members(party_id)
        voted = {(v["user_id"], v["rank"]) for v in await self.parties.list_votes(party_id)}
        if all((m["user_id"], p["rank"]) in voted for m in members for p in proposals):
            return await self._finish(party_id, user["id"])
        return await self.state(party_id, user["id"])

    async def close(self, party_id: str, user: Optional[dict]) -> dict:
        party = await self._party(party_id)
        if user is not None:
            self._require_starter(party, user)
        self._require_status(party, "voting")
        return await self._finish(party_id, user["id"] if user else party["starter_id"])

    async def cancel(self, party_id: str, user: dict) -> dict:
        party = await self._party(party_id)
        self._require_starter(party, user)
        self._require_status(party, "joining", "voting")
        if await self.parties.set_status(party_id, "cancelled", at=self.clock()):
            await self._bot_say(f"Soirée annulée par {_name(user)}.")
        return await self.state(party_id, user["id"])

    async def _finish(self, party_id: str, viewer_id: str) -> dict:
        proposals = await self.parties.list_proposals(party_id)
        if not proposals:
            await self.parties.set_status(party_id, "empty", at=self.clock())
            return await self.state(party_id, viewer_id)
        winner_rank = tally(proposals, await self.parties.list_votes(party_id))["winner_rank"]
        winner = next(p for p in proposals if p["rank"] == winner_rank)
        if await self.parties.set_status(party_id, "done", at=self.clock(), winner_tmdb_id=winner["tmdb_id"]):
            when = f" à {winner['showtime']['time']}" if winner.get("showtime") else ""
            await self._bot_say(f"🏆 Ce soir : {winner['title']}{when}")
        return await self.state(party_id, viewer_id)

    # --- Salon --------------------------------------------------------------

    async def handle_chat_message(self, body: str, user: dict) -> Optional[dict]:
        """Répond à @soirée : l'annonce est publique, l'aide et les refus ne vont qu'à l'auteur."""
        if not is_party_command(body):
            return None
        argument = " ".join(_COMMAND_RE.match(_fold(body.strip())).group(1).split())
        mode = {"coloc": "coloc", "cine": "cinema", "cinema": "cinema"}.get(argument)
        if mode is None:
            return await self._bot_say(
                "Lance une soirée :", {"type": "cine_help", "commands": HELP_COMMANDS}, visible_to=user["id"],
            )
        try:
            await self.start(user, mode)
        except PartyError as error:
            return await self._bot_say(error.message, visible_to=user["id"])
        return None
