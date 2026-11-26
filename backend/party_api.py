"""Routes de la soirée film du salon."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api import get_store
from backend.auth_api import AuthContext, get_current_user
from backend.core.party_service import PartyError, PartyService
from backend.core.store import MediaStore

party_router = APIRouter(prefix="/api/parties", tags=["parties"], dependencies=[Depends(get_current_user)])


class StartPartyRequest(BaseModel):
    mode: Literal["coloc", "cinema"]


class AnswersRequest(BaseModel):
    answers: dict[str, str]


class VoteRequest(BaseModel):
    rank: int
    value: Literal[1, -1]


async def _call(action):
    try:
        return await action
    except PartyError as error:
        raise HTTPException(status_code=error.status, detail=error.message) from error


@party_router.post("")
async def create_party(
    payload: StartPartyRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    return await _call(PartyService(store).start(current.user, payload.mode))


@party_router.get("/{party_id}")
async def get_party(party_id: str, current: AuthContext = Depends(get_current_user), store: MediaStore = Depends(get_store)):
    return await _call(PartyService(store).state(party_id, current.user["id"]))


@party_router.post("/{party_id}/join")
async def join_party(party_id: str, current: AuthContext = Depends(get_current_user), store: MediaStore = Depends(get_store)):
    return await _call(PartyService(store).join(party_id, current.user))


@party_router.post("/{party_id}/answers")
async def answer_party(
    party_id: str,
    payload: AnswersRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    return await _call(PartyService(store).answer(party_id, current.user, payload.answers))


@party_router.post("/{party_id}/launch")
async def launch_party(party_id: str, current: AuthContext = Depends(get_current_user), store: MediaStore = Depends(get_store)):
    return await _call(PartyService(store).launch(party_id, current.user))


@party_router.post("/{party_id}/votes")
async def vote_party(
    party_id: str,
    payload: VoteRequest,
    current: AuthContext = Depends(get_current_user),
    store: MediaStore = Depends(get_store),
):
    return await _call(PartyService(store).vote(party_id, current.user, payload.rank, payload.value))


@party_router.post("/{party_id}/close")
async def close_party(party_id: str, current: AuthContext = Depends(get_current_user), store: MediaStore = Depends(get_store)):
    return await _call(PartyService(store).close(party_id, current.user))
