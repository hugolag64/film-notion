import asyncio

import pytest
from fastapi import HTTPException

from backend.api import PostChatMessageRequest, list_chat_messages, post_chat_message
from backend.auth_api import AuthContext
from backend.core.store import MediaStore


def _store(tmp_path):
    store = MediaStore(str(tmp_path / "chat.db"))
    store.init_schema()
    return store


def _user(user_id="hugo", name="Hugo"):
    return AuthContext(
        user={"id": user_id, "role": "user", "display_name": name, "avatar_url": None},
        session_id="session",
        token="token",
    )


def test_posted_message_is_signed_with_author_and_listed(tmp_path):
    store = _store(tmp_path)

    posted = asyncio.run(post_chat_message(PostChatMessageRequest(body="  Salut 🎬  "), _user(), store))
    listed = asyncio.run(list_chat_messages(None, _user("lea", "Léa"), store))

    assert posted["body"] == "Salut 🎬"
    assert posted["author"] == {"id": "hugo", "display_name": "Hugo", "avatar_url": None}
    assert [message["id"] for message in listed["messages"]] == [posted["id"]]


def test_listing_after_a_cursor_only_returns_newer_messages(tmp_path):
    store = _store(tmp_path)
    first = asyncio.run(post_chat_message(PostChatMessageRequest(body="un"), _user(), store))
    second = asyncio.run(post_chat_message(PostChatMessageRequest(body="deux"), _user("lea", "Léa"), store))

    listed = asyncio.run(list_chat_messages(first["id"], _user(), store))

    assert [message["body"] for message in listed["messages"]] == ["deux"]
    assert second["id"] > first["id"]


def test_listing_without_cursor_returns_latest_messages_oldest_first(tmp_path):
    store = _store(tmp_path)
    for index in range(60):
        asyncio.run(store.create_chat_message("hugo", "Hugo", None, f"m{index}"))

    listed = asyncio.run(list_chat_messages(None, _user(), store))

    bodies = [message["body"] for message in listed["messages"]]
    assert len(bodies) == 50
    assert bodies[0] == "m10"
    assert bodies[-1] == "m59"


@pytest.mark.parametrize("body", ["", "   ", "x" * 501])
def test_empty_or_too_long_messages_are_rejected(tmp_path, body):
    store = _store(tmp_path)

    with pytest.raises(HTTPException) as error:
        asyncio.run(post_chat_message(PostChatMessageRequest(body=body), _user(), store))

    assert error.value.status_code == 400
