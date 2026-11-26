import asyncio

import pytest
from fastapi import HTTPException

from backend.api import PostChatMessageRequest, post_chat_message
from backend.auth_api import AuthContext
from backend.core.party_store import PartyStore
from backend.core.store import MediaStore
from backend.party_api import (
    AnswersRequest, StartPartyRequest, VoteRequest, answer_party, create_party, get_party, join_party, vote_party,
)


def _store(tmp_path):
    store = MediaStore(str(tmp_path / "api.db"))
    store.init_schema()
    return store


def _user(user_id="hugo", name="Hugo"):
    return AuthContext(
        user={"id": user_id, "role": "user", "display_name": name, "avatar_url": None},
        session_id="session",
        token="token",
    )


def test_routes_map_party_errors_to_http_status(tmp_path):
    store = _store(tmp_path)
    state = asyncio.run(create_party(StartPartyRequest(mode="coloc"), _user(), store))

    with pytest.raises(HTTPException) as error:
        asyncio.run(create_party(StartPartyRequest(mode="cinema"), _user("lea", "Léa"), store))
    assert error.value.status_code == 409
    assert error.value.detail == "Une soirée est déjà en cours."

    with pytest.raises(HTTPException) as error:
        asyncio.run(get_party("inconnue", _user(), store))
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        asyncio.run(vote_party(state["id"], VoteRequest(rank=1, value=1), _user("tom", "Tom"), store))
    assert error.value.status_code == 403


def test_join_and_answer_through_routes(tmp_path):
    store = _store(tmp_path)
    state = asyncio.run(create_party(StartPartyRequest(mode="cinema"), _user(), store))

    asyncio.run(join_party(state["id"], _user("lea", "Léa"), store))
    answered = asyncio.run(answer_party(
        state["id"], AnswersRequest(answers={"mood": "any", "runtime": "105"}), _user("lea", "Léa"), store,
    ))

    assert answered["me"] == {"member": True, "answered": True, "votes": {}}
    assert [m["name"] for m in answered["members"]] == ["Hugo", "Léa"]


def test_chat_command_starts_a_party(tmp_path):
    store = _store(tmp_path)

    asyncio.run(post_chat_message(PostChatMessageRequest(body="@soirée coloc"), _user(), store))

    party = asyncio.run(PartyStore(store.db_path).active_party())
    assert party["mode"] == "coloc"
    assert asyncio.run(store.list_chat_messages(None))[-1]["payload"]["type"] == "party"
